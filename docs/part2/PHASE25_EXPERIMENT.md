# Phase 25 protocol — Mechanic slot-2 replay probe (non-scoring)

**Status: approved for launch by Claude (PM, delegated by project owner Shree Bohara) on 2026-09-25; declared before any paid call.** Review rounds 1, 2 and 3 are applied, and round 3's fixes were checked by a focused verification (see the Review log's closing entry). The harness enforces the review through the line below and `artifacts/phase25-2026-09-24/review.json`. No provider call has been made for this phase before launch.

Reviewed for launch: harness 28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0 plan 5db5c880905661cc37c1e813ef860e9e6c26d9e7e9ccbf50fb4730c2ea434df5

## 1. The question

A completion study asks the Mechanic for a policy twice (`PROPOSAL_SLOTS = 2`). In most studies
the second answer is the same policy as the first, so a study gets one real draw, not two
(pitfall 70). In the two v4-era full-loop runs, 18 of the 26 studies that asked for slot 2 got
slot 1's policy back on the first attempt (§2).

Two questions, both on stored development requests:
1. **Why does slot 2 repeat slot 1?** The code and the store say what differs between the two
   requests ($0, §2). They cannot say whether the model copies the prior candidate or re-derives
   the same policy from similar evidence. Arm H (the exact prior text withheld) and the reference
   arm N (no prior candidate at all) test that.
2. **Does one declared change to the slot-2 request give proposals that are distinct from slot 1
   and whose retry step fires, with no declared harmful side rule, without more invalid output?**
   Two changes are tested separately: a higher temperature (T) and withholding the exact text of
   the prior proposal (H).

This is a **replay probe**. It re-sends stored Mechanic requests and reads the policies that come
back. It runs no episode, scores nothing, and creates no campaign, study, trial, world, policy
or store row. A positive result is only a recommendation for a later loop, which would need its
own declaration, a `backend/app` change, a new configuration and a new freeze (§8.5).

## 2. What the code and the store show ($0)

### 2.1 How the slot-2 request is built

`completion_study._execute` builds both slots with the same code, and `Mechanic._generate` sends
them:

```
[{system: prompts/completion.md},
 {user: canonical_json({**proposal_context, 'output_schema': MechanicOutput JSON schema})}]
```

For slot 2, `proposal_context` differs from slot 1's in three of its ten fields:
- **`candidate_history`** is `deepcopy(record['candidates'])`. For slot 1 it is empty. For slot 2
  it holds one entry, slot 1's proposal, with the keys `content`, `decision`, `explanation`,
  `policy_hash`, `policy_version`, `proposal_ref`, `raw_outputs` and `source_assessment`. So
  slot 1's policy appears **twice**:
  - `content`: the policy as canonical JSON, with sorted keys and an `only_if` on every step;
  - `raw_outputs`: the exact text the Mechanic wrote, as a JSON string.
- **`development_evidence`** and **`observed_outcomes`** gain slot 1's six source episodes (3
  pairs). A study reaches slot 2 only when slot 1 did not qualify at the source, so all 26 studies
  carry them.

### 2.2 What the stored slot-2 requests produced

**Census:** all 26 v4-era studies that asked for slot 2 (5 from Phase 17, 21 from Phase 23; §5).
Figures are for each slot-2 request's **first attempt**, from `dry-plan-r3/investigation.json` and
`protocol-numbers/protocol_numbers-r3.out.json` (both identical to rounds 1 and 2 in these figures).

| finding | count |
|---|---|
| the slot-2 input differs from slot 1's (`candidate_history`, `development_evidence`, `observed_outcomes`) | 26 of 26 |
| the slot-2 user message is larger by | 15,627 to 20,522 bytes (slot 1: 27,529–31,051; slot 2: 44,848–49,974) |
| provider input tokens, slot 1 / slot 2 (median; range) | 9,378 (8,572–9,812) / 15,704 (14,828–16,777) |
| slot 1's exact text is in the slot-2 input (inside `raw_outputs`, as an escaped JSON string) | 26 of 26 |
| **the output is the same policy as slot 1** (the study's DUPLICATE rule: equal policy hash) | **18 of 26** (Phase 17: 2 of 5; Phase 23: 16 of 21) |
| the final slot-2 decision was DUPLICATE (the study allows one format repair) | 19 of 26 (Phase 17: 3 of 5; Phase 23: 16 of 21) |
| the output is byte-identical to slot 1's output | 1 of 26 |
| the output's rules text is byte-identical to slot 1's (layout included) | 18 of 26: 17 of the 18 duplicates, plus the 1 first attempt that failed the schema |
| **the same policy written twice with no prior candidate in view:** v4 studies whose slot-1 first attempts are the same policy (different inputs, empty `candidate_history`) | **6 pairs; the rules text is byte-identical in 5** (census only: 4 of 5); the whole output in 0 |
| duplicates whose explanation says "materially different" | 16 of 18 |
| duplicates whose explanation mentions a retry while the policy has no notification retry step | **10 of 18** (7 say "bounded retry"; 4 use the words "adds a bounded retry of the original notification request") |
| distinct outputs | 7 of 26: 5 without the step, 1 with a dead step (`4cdc240c…`), 1 whose step fires (`0a2ff2e6…`). That one defers before waiting (a declared harmful side rule), so it is **not WORKING** (§7); in validation it lost terminal rejection, 0 against 3 |
| slot-1 policies whose step already fires | 2 of 26 (`cc22dd0a`, `469b9cd7`); `0a2ff2e6…` is `cc22dd0a`'s slot-1 policy lightly edited (round-1 review) |
| slot-1 policies across the 26 studies (how often evidence alone repeats a policy) | 22 distinct; 5 of 325 cross-study pairs coincide; `89027787…` was slot 1 in three studies |

**Where the repeated text sits.** For the 18 first attempts whose rules text equals slot 1's:
- that text occurs in the input **only** as the escaped string inside `raw_outputs` (18 of 18),
  never verbatim;
- the canonical `content` beside it is laid out differently: slot 1's raw rules have a key order
  other than sorted (18 of 18), and in 16 of 18 at least one raw step has no `only_if`, while
  `content` has one on every step.

**Reading.**
- **Same-input determinism is ruled out.** The two requests are different inputs (26 of 26),
  and in 25 of 26 the slot-2 output differs from slot 1's somewhere, usually in the explanation.
  Whether greedy decoding at temperature 0 *contributes* is what arm T measures. Phase 21 found
  temperature 0 is not deterministic for the Actor model on this provider (36% of repeat pairs
  byte-identical); for the V4 Mechanic it is unmeasured, and C and H measure it here.
- **Hypothesis, not a finding:** the duplicates coincide with the prior candidate being in the
  input. **Layout identity does not show copying.** When the model writes the same policy twice
  with no prior candidate at all (different studies, slot 1), the rules text is byte-identical in 5
  of 6 such pairs: the layout is the model's own style. So an identical layout cannot tell copying
  of `raw_outputs` from re-deriving the same policy. (Round 0 of this protocol called the copy
  "confirmed"; review round 1 refuted that, see the Review log.)
- **What the experiment decides.** Arm H withholds the exact prior text and keeps the canonical
  prior policy. Arm N removes the prior candidate altogether and keeps the slot-2 evidence, which
  includes slot 1's source episodes. If duplicates fall under H, the exact text matters. N's rate of
  writing slot 1's policy says how often the slot-2 evidence alone leads back to it. Both are read
  in §8.3.

## 3. What is fixed

**Setup.**
- Mechanic model `deepseek-ai/DeepSeek-V4-Pro-0813`, called directly through the runtime's own
  `RuntimeProvider` (W&B Inference), with no Weave tracing.
- Frozen request settings, checked against the frozen configuration and `MODEL_REQUEST_SETTINGS`:
  temperature 0, 2,000 output tokens, `response_format` `json_object`, thinking disabled
  (`extra_body.chat_template_kwargs.enable_thinking = false`), 20 s timeout, no provider retry.
- The Phase 17 settings file on the Phase 22 code. No file under `backend/app` changes.
- Development data only. heldout-2 is spent and is never read, listed or used
  (`PHASE22_EXPERIMENT.md` §7.5). No held-out partition or seed, promotion record or final-audit
  file is read.
- **`checks.py` is never read by a person or an agent.** Like every configuration recompute since
  Phase 13 (Phases 20 and 21 included), the fingerprint code hashes the `backend/app` tree, which
  includes `checks.py`, `heldout_check.py` and `promotion.py` as source files, and it imports
  `scorer_hash`. (Round 0 said `checks.py` "is never opened"; that was literally false, see the
  Review log.)
- No result is shown to any model, enters any study, or tunes anything.

**Pins.**

| item | value |
|---|---|
| harness `scripts/experiments/slot2_probe.py` sha256 | `28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0` |
| plan hash (`content_hash(plan)`) | `5db5c880905661cc37c1e813ef860e9e6c26d9e7e9ccbf50fb4730c2ea434df5` |
| `dry-plan-r3/plan.json` sha256 | `ce5cb3ffb6823c1f1eb201de6a998ae462c9c3a414cd11401ad26f064fab186d` |
| `configuration_hash` (Phase 17 settings on the Phase 22 code), recomputed with `.env` unread | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba` |
| settings `artifacts/phase16-2026-09-22/settings-phase17.json` sha256 | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| Phase 22 freeze `artifacts/phase22-2026-09-24/gate-freeze-after.json` sha256 | `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1` |
| census configurations | Phase 17 `c4169ee49deb7fb27ac44205d6e74b4f89912d1b43bf945636745b1872110418`; Phase 23 `2cf63e93…` (above) |
| Phase 17 run manifest `artifacts/phase17-2026-09-23/full-loop-manifest.json` sha256 | `f90605404d00a3c43107ef0165b15bb0acad87207e873c8ad2d7421480f63830` |
| Phase 23 run manifest `artifacts/phase23-2026-09-24/full-loop-manifest.json` sha256 | `aac41711ea8df103ed1c5bdb6df7a75275d019f60c716a9a0aaf102b7b31b6f5` |
| store cutoff | `2026-09-24T05:50:00Z` (Phase 23's last study was created at 05:42:09Z; Phase 24 created none) |
| per-request dollar bound | $0.04984 (32,000 input × $1.31/M + 2,000 output × $3.96/M; frozen Mechanic pricing) |
| tests sha256 (not pinned by the harness) | `16f4b4a0fab711d52f9f961d89b90f2880a43e4e24c465084924c1a177c0e36c` |
| protocol-numbers script sha256 (not pinned) | `d1f1a70f8905cf3d355cde3d0d7b09bab6b04d66462b145344eb896321d8ebaf` |
| protocol-numbers output `protocol_numbers-r3.out.json` sha256 | `f0aaa420338401df0ab6b9aed6f3a32908a16655ed7e8e0625f518af5ba01173` |
| this document | its sha256 is typed by the operator (`--expect-protocol-sha256`) and repeated in the review record; the harness never pins it, so the pins are not circular |

- **The freeze is checked without running `gate_freeze.py`,** which hashes held-out and audit
  files this phase must not read. The harness instead compares the freeze file's sha256, its five
  recorded fingerprints (`source_hash`, `runtime_hash`, `contract_hash`, `algorithm_hash`,
  `interpreter_hash`) with the recomputed configuration's, and its recorded hashes of
  `completion.md`, `mechanic.py`, `diagnosis.py`, `completion_study.py` and `policies.py` with
  the files.
- The plan also records the sha256 of nine source files the rebuild depends on (those five plus
  `contracts/models.py`, `providers/runtime.py`, `policy_state.py` and `policy_interpreter.py`).
  Any change moves the plan hash, and the live gate refuses.
- **Only in-scope studies are counted in the plan.** The hashed plan counts only completion studies
  of the two declared configurations created before the cutoff (`excluded_in_scope`). Store-wide
  counts (166 studies of other configurations today) are in `dry-summary.json` only, so a study
  added to the store later, by any phase, cannot move the plan hash. (Round 0 put store-wide counts
  in the plan; see the Review log.)
- **The dry run never reads `.env`** (`env_path=os.devnull`); a test checks this. A live run reads
  it once, after every offline check, through the runtime's own loader. Both API keys are scrubbed
  from every file the run writes, including a traceback.

## 4. How a request is rebuilt and verified

**No Mechanic request hash is stored anywhere.**
- `mechanic_outputs` keeps the raw text, model, attempt, `request_id` and usage.
- `completion_proposal_inputs` keeps the context.
- Only the Actor's `actor_output` events carry request hashes (the basis of Phase 21's check).

So the program's "verify each against its stored hash" cannot be done as written. A request is
used only if **all twelve** checks in `verify_slot()` hold (eleven for slot 1, which has no
`slot1_reference`). A prompt that fails is counted and reported, and it is never sent.

| check | what it compares |
|---|---|
| `input_record_immutable` | the `completion_proposal_inputs` row exists and is immutable |
| `stored_payload_canonical` | the stored payload text equals `canonical_json` of the context, byte for byte (`put_record` stores `canonical_json(payload)`) |
| `context_keys` | exactly the ten keys `_execute` writes |
| `fixed_fields` | campaign, study, objective, parent `policy-v0`, and both fault specs from the study manifest |
| `candidate_history` | equals the study record's earlier `candidates` (a separate record, saved later) |
| `observed_outcomes` | recomputed by the runtime's own `trial_outcomes` from the study's stored trial rows |
| `development_evidence` | recomputed by the runtime's own `summarize_evidence` from the stored `evidence` bundles |
| `runtime_contract` | equals the code's `runtime_contract()` |
| `configuration_source_and_contract` | the study configuration's `source_hash` (the tree hash of `backend/app/agents`, which includes `completion.md` and `mechanic.py`), `contract_hash`, `dependency_lock_hash`, `model_settings_by_role` (every role's request settings) and Mechanic model equal the pinned configuration's |
| `historical_output` | the attempt-0 `mechanic_outputs` row: prompt, model and campaign match, and every attempt's raw text equals the candidate's `raw_outputs` |
| `provider_token_fingerprint` | the provider's own `prompt_tokens` for that request equals the vendored DeepSeek-V4 tokenizer's count of the rebuilt roles and contents **+ 24** (the two-message chat template; exactly 24 on all 52 stored requests) |
| `slot1_reference` (slot 2 only) | slot 1's policy hash, recomputed from its stored raw text, equals the study's |

- **Result: 52 of 52 slots verify** (26 studies × 2 slots), 0 failures.
- **The token fingerprint is a count, not a hash.** A test shows a same-count substitution
  (`policy-v0` → `policy-v9`) keeps it. The byte-level claim rests on the recomputation checks;
  the fingerprint is the only evidence from the provider's side of what was sent.
- **Parity with the runtime's own code, on every prompt:** for all 52 stored contexts, and for the
  C, H and N prompt of all 26 studies, the rebuilt messages equal what the real
  `Mechanic.propose_completion` sends for that context (captured with a fake provider). A fake
  client behind the real `RuntimeProvider` receives exactly the planned request digests. (Round 0
  tested 4 of 52; see the Review log.)
- **What covers `contracts/models.py` for the 5 Phase 17 prompts.** The user message depends on
  `output_schema` and `canonical_json`, both in `contracts/models.py`, which neither `source_hash`
  nor `contract_hash` covers. For the 21 Phase 23 prompts, `runtime_hash` (the whole `backend/app`
  tree) is the pinned configuration's and matches the Phase 22 freeze. The Phase 17 configuration
  (`c4169ee4…`) differs from the pinned one only in `adapter_hash`, `algorithm_hash` and
  `runtime_hash`. So for those 5 prompts `models.py` is covered by the equal dependency lock, the
  file being unchanged since before Phases 16 and 17 (modified September 20), the parity and
  stored-bytes checks, and the token fingerprint; not by a hash.
- The store is opened read-only (`?mode=ro`).

## 5. Populations (exact counts)

**Census, with no sampling.** Every completion study in the read-only store that has:
- configuration `c4169ee4…` (Phase 17) or `2cf63e93…` (Phase 23);
- the v4 Actor context and evidence protocol v2;
- no `replay_of`;
- `created_at` before the cutoff;
- two proposals.

**The census must equal the studies with two proposals in the two pinned run manifests**, or
planning refuses. It does: **5 + 21 = 26 studies.** Excluded in scope: 13 v4 studies that never
reached slot 2.

| arm | prompts | draws per prompt | requests |
|---|---|---|---|
| C | 26 slot-2 prompts | 3 | 78 |
| T | the same 26 | 3 | 78 |
| H | the same 26 (H context) | 3 | 78 |
| N (reference) | the same 26 (N context) | 1 | 26 |
| **total** | **78 distinct prompts** | | **260** |

Slot 1 is verified (the census, the token fingerprint and the investigation use it) but never
re-sent. Round 0's slot-1 reference arm C1 is replaced by N (§6, Review log).

**Order** (fixed by seeded sha256 ranks, seed `faultlab-phase25-2026-09-24`):
1. **Round 1, `r0001`–`r0104`:** prompts by rank, and each prompt's C, T, H and N back to back, in
   ranked order;
2. **rounds 2 and 3, `r0105`–`r0260`:** C, T and H of each prompt back to back, each round ranked
   afresh.

**What a short run leaves** (plain consequences; §8.6 declares the fallback):
- A stop before round 1 is complete leaves every decision `INCOMPLETE`. Each slot-2 arm can first
  reach 25 of its 26 round-1 draws at `r0097`–`r0100`; round 1 ends at `r0104`.
- A stop after round 1 but before the arms can reach 75 of 78 draws (`r0249` for H, `r0250` for T,
  `r0251` for C) makes the all-rounds decisions `INCOMPLETE`. If the stop is one the operator does
  not choose (the spend guard, five errored requests in a row, a crash recorded with its traceback),
  the declared decisions are then the round-1 fallback's, labelled "round 1 only" (§8.6). Its power
  is lower (§9.3). **After an operator stop** (any SIGINT or SIGTERM, whoever sent it, or a process
  killed and closed with `--finalize-abandoned`) they stay `INCOMPLETE` (review rounds 2 and 3).
- A run that delivered any generation can never be followed by another run (§10). There is no
  continuation mode: a later run would re-draw requests after their partners were seen.

**Prompts are not fully independent.** 26 studies share 22 slot-1 policies (`89027787…` is slot 1
in three studies; two other policies in two each), so their slot-2 prompts carry the same prior
candidate and similar evidence. The effective number of independent prompts is below 26, and the
sign-test p-values are somewhat optimistic. A sign test with prompts collapsed by slot-1 policy
(22 clusters) is reported beside each declared one, descriptive only (§8.4, §14).

## 6. Arms (exact)

Every request is the `chat.completions.create()` call `RuntimeProvider.complete` makes for the
Mechanic role:

```
model="deepseek-ai/DeepSeek-V4-Pro-0813",
messages=[{"role": "system", "content": <backend/app/agents/prompts/completion.md>},
          {"role": "user",   "content": canonical_json({**context, "output_schema": <MechanicOutput schema>})}],
max_tokens=2000, response_format={"type": "json_object"}, temperature=<arm>, stream=False,
extra_body={"chat_template_kwargs": {"enable_thinking": False}}
(plus timeout=20, which is not part of the request digest)
```

| arm | `context` | temperature |
|---|---|---|
| **C** (control) | the verified stored slot-2 context, unchanged | 0 |
| **T** (temperature) | the same as C, byte for byte | **0.7** |
| **H** (prior text withheld) | the slot-2 context with **`raw_outputs` removed** from every `candidate_history` entry; `content`, `explanation`, `decision`, `policy_hash`, `policy_version`, `proposal_ref` and `source_assessment` stay | 0 |
| **N** (reference: no prior candidate) | the slot-2 context with **`candidate_history = []`**; `development_evidence` and `observed_outcomes`, which carry slot 1's six source episodes, stay | 0 |

- **T** changes only the `temperature` keyword. 0.7 is the value the earlier program declared
  (`EXPERIMENT_PROGRAM_PHASES_20-27.md`, Phase 26(c): "T=0 vs T=0.7"). `RuntimeProvider` builds the
  frozen request at temperature 0; the harness's client wrapper checks that, sets the arm's
  temperature, recomputes the request digest and forwards the request only if the digest equals
  the plan's `request_hash` (§10).
- **H** is built in the harness only. It removes about 660 input tokens (median 15,704 → 15,043).
  The prior candidate still appears once, in canonical form, with its explanation.
- **N** is built in the harness only (median 14,357 input tokens). It is the evidence-alone
  reference: how often the model, at temperature 0, writes slot 1's policy from the slot-2
  evidence with no prior candidate in view. Its user message holds neither slot 1's raw text nor
  its policy hash (26 of 26). One draw per prompt; descriptive; it decides nothing.
- **Why N replaced C1.** Round 0's reference C1 re-sent slot 1's own request at temperature 0. Its
  "reproduces slot 1" rate was by construction the same event as its agreement with slot 1's
  historical output (slot 1's policy is the historical output's on 25 of 26 prompts), so it measured
  same-input determinism, and it lacked the six slot-1 source episodes the slot-2 evidence carries.
  It could not separate "copies the prior candidate" from "re-derives slot 1's policy from the slot-2
  evidence". N can. The request count ($12.96 bound) is unchanged.

**Why H withholds only the exact text, not the whole prior candidate** (a deviation from the old
program's "hidden-prior-candidate" arm, decided before any data):
- It is the smallest change a later loop could adopt, and it separates two hypotheses the round-0
  reading ran together: the exact text is what is repeated, or the policy is (the canonical
  `content` stays in H). §2 does not show which: layout identity also arises without a prior
  candidate (5 of 6 pairs).
- The explanations show the model trying to write "the prior policy plus a retry". That needs
  the prior content, so hiding everything in the treated arm would remove the text and that
  information at once. The no-prior-candidate case is measured instead by the reference arm N.
- **Its limit:** if the model repeats the canonical `content` instead, H cannot show an effect of
  the text. The mechanism read-out then says `NOT_SHOWN`, with N quoted beside it.

**The $0 pre-check passed** (`precheck` in the plan). Its rows compare each arm's request with C's
request; they are real checks, not self-checks. Nothing may be sent if it fails.

| check | result |
|---|---|
| T differs from C only in `temperature` | 26 of 26 |
| H with the withheld key restored equals C's context; same system message and settings | 26 of 26 |
| H keeps the prior canonical `content` | 26 of 26 |
| no slot-1 raw text is left in H's user message | 26 of 26 |
| N with `candidate_history` restored equals C's context; same system message and settings | 26 of 26 |
| N's user message has an empty `candidate_history` and holds neither slot 1's raw text nor its policy hash | 26 of 26 |

## 7. The static auditor

Each returned text is judged as the study would judge it:
- `MechanicOutput.validate_json`; empty or unparseable output is `INVALID`;
- a `MechanicNoChange` is `NO_CHANGE`;
- the `policy-v0` parent check (`STALE_PARENT`) and the `CandidatePolicy` re-validation from
  `policies.proposal` (`INVALID`);
- otherwise `CANDIDATE`, with policy hash `content_hash(candidate)`. A candidate is **DUPLICATE**
  if its hash equals slot 1's, else **DISTINCT**. This is the study's DUPLICATE rule.

No format-repair turn is sent: one request is one draw (the study would allow one repair; this is
recorded in the plan).

On every candidate, an abstract run of `PolicyInterpreter.invoke` (its `condition()` is pinned
by a test to the runtime's `PolicyState.condition` for every condition, state and flag):
- **Step present:** a notifications `retry_original_request` at `after_notification_response`
  (the Phase 9 predicate).
- **Step fires**, along the source case (`notification-2`):
  1. `after_upgrade_response`: the upgrade succeeded with a matching receipt;
  2. `before_confirmation`: the Actor proposes its first send;
  3. `after_notification_response`: the send failed transiently: notifications attempted, no
     receipt, status `UNKNOWN`, and a status read returns `UNKNOWN`, never `PENDING` (pitfall 77).

  The step fires if a notifications retry executes at step 3 and nothing earlier closed
  business, blocked the send, or exhausted the 32 policy steps or 4 wait cycles.
- **Side rules:**
  - `premature_defer` (pitfall 78): at `after_upgrade_response`, with the upgrade attempted,
    unreceipted and `PENDING`, and a status read still `PENDING`, a `defer_unresolved` executes
    before any `wait_ticks`;
  - `stops_first_confirmation`: on steps 1–2 above (the upgrade succeeded, the first send is
    proposed; the same on the healthy case), a rule closes business, blocks the send, or
    exhausts a bound.

  **Harmful** = either one. `orders_retry` is recorded, descriptive only.
- **WORKING** = DISTINCT, the step fires, and not harmful. **Distinct firing** = DISTINCT and the
  step fires, harmful or not. (Round 0 called distinct firing "working"; review round 1 showed that
  counted premature-defer policies, which lose terminal rejection in validation, as yield.)

**Validated against what stored v4 candidates did ($0):**
- "fires" against a policy-dispatched `send_confirmation` in the candidate's own triggered source
  trials: **40 of 40 agree** (10 predicted to fire and fired every time, 30 predicted silent and
  never fired);
- `premature_defer` against the terminal-rejection case wherever validation ran: the 2 flagged
  policies both lost it (L correctly rejected 0 of 3 against B0's 3 of 3); the 4 certified
  policies were unflagged and did not;
- across 35 distinct v4 policies: 4 harmful, 11 with the step, 2 with a dead step. **Harm is not
  spread evenly: 3 of the 9 policies whose step fires are harmful, against 1 of the 26 whose step
  does not** (`harm_model_from_store` in the numbers output). The simulations use these rates.

## 8. Declared read-outs and the decision rule

### 8.1 Units and classes

- **A draw is one planned request.** Classes: `INVALID`, `NO_CHANGE`, `STALE_PARENT`, `CANDIDATE`
  (DUPLICATE or DISTINCT).
- **Received** means a generation arrived (`ok` or `empty_response`). An empty response is a
  received `INVALID`. A request that errored after its one blind retry, and after its one re-send
  if the run reached the re-send pass (§10), is missing. A request with a main-pass line and a
  re-send line is read from the received line.
- **Complete:** an arm received at least 95% of its planned draws: **75 of 78** over all rounds,
  **25 of 26** in round 1.

### 8.2 Recommendation rule, for T and for H separately (each against C)

Rates, with every missing draw counted against the treated arm X (worst case):
- **D_X** = X's DISTINCT draws / 78 planned; **D_C** = (C's DISTINCT + C's missing) / 78.
- **Working share** (review round 2). Only the **24 prompts whose slot-1 policy's step does not
  fire** are eligible (the 2 others cannot show a step the change produced; their working draws are
  reported separately, §8.4). On an eligible prompt, X's share is its WORKING draws / its planned
  draws (a missing X draw is not WORKING), and C's share is its WORKING **or missing** draws / its
  planned draws. The **gain** is the sum, over the eligible prompts, of X's share minus C's. Each
  prompt adds between −1 and +1. With 3 planned draws per prompt in every arm, a gain of g means 3g
  more WORKING draws in X than WORKING-or-missing draws in C, over the 72 eligible draws of each arm.
- **Invalid** = (`INVALID` + `STALE_PARENT`) / received, per arm.
- **Harmful share of firing** = X's distinct firing draws that are harmful / X's distinct firing
  draws (0 if X has none).

The decision is **`RECOMMEND_FOR_A_LATER_LOOP`** only if every condition holds (the harness's
condition names):

| # | condition | name |
|---|---|---|
| 1 | X and C are complete | `complete` |
| 2 | D_X ≥ 0.70 | `distinct_at_least_0.70` |
| 3 | D_X − D_C ≥ 0.30 | `distinct_gain_at_least_0.30` |
| 4 | one-sided exact sign test over prompts, on each prompt's mean DISTINCT over its received draws, X above C, ties and prompts without draws in both arms dropped: p < 0.05 | `sign_test_p_below_0.05` |
| 5 | working-share gain ≥ **10/3** (10 more WORKING draws of 72) | `working_share_gain_at_least_3.33` |
| 6 | invalid_X − invalid_C ≤ 0.10 | `invalid_at_most_C_plus_0.10` |
| 7 | harmful share of X's distinct firing draws ≤ 0.50 | `harmful_share_of_firing_at_most_0.50` |

- If condition 1 fails the decision is **`INCOMPLETE`** (and §8.6 applies). Otherwise, if any
  condition fails, it is **`NOT_RECOMMENDED`**. Every failed condition is listed either way.
- **The prompt is the unit of inference.** The sign test (condition 4) is a test; condition 5 is a
  sum of per-prompt contrasts whose threshold was chosen by simulation so that it has a false-alarm
  rate (§9.2); the rate thresholds are effect-size floors. The 3 draws of one prompt are not
  independent, and neither are prompts that share a slot-1 policy (§5).
- **Why condition 5 is a per-prompt share, and why 10/3.**
  - **Round 0** counted draws (W_X − W_C ≥ 0.05, 4 draws). One or two prompts could supply that by
    noise, and under "X more distinct, no more working than C" it recommended 7–26% of the time.
  - **Round 1** counted prompts with at least one WORKING draw among three (minimum 6). That count
    measures **breadth, not per-draw yield**: at equal per-draw WORKING rates it favours the arm whose
    draws vary more within a prompt. T at 0.7 against C at 0 differs in exactly that way, and a loop
    that takes one slot-2 draw per study gains only from the per-draw rate. With C clustered and X
    not, its false-alarm rate rose above 0.05 (Review log, round 2, G1).
  - **Round 2's share** fixes both. Each prompt adds at most 1, so one prompt cannot supply the
    threshold. Its expectation is 0 at equal per-draw rates however the draws cluster.
  - **Round 3: an arm at temperature 0 may repeat its own output.** C and H are both at temperature
    0, and the Mechanic's temperature-0 determinism is unmeasured (§2.2). If every repeat of a prompt
    returns that prompt's first draw, each prompt's share is 0 or 1 and the gain is a whole number, so
    round 2's minimum of 8/3 acted as a count of 3 prompts, a count the round-1 fallback's own table
    rejects (worst cell 0.0722 at 3, §9.2).
    Round 2's grid could not reach this case: its Beta model draws each draw's class and harm
    independently, however large ρ is. The round-3 reviewer measured P(`RECOMMEND`) at 8/3 of
    0.055–0.069 under this null (Review log, round 3, finding 1).
  - **10/3** is the smallest multiple of 1/3 for which P(`RECOMMEND`) under the yield null is at most
    0.05 in every scenario the numbers script runs: the six Beta clustering scenarios (the three of
    round 1; C clustered with X not or mildly, and X clustered with C not, from round 2), six repeat
    scenarios (round 3: both arms repeat at q 0.9 and 1.0; C repeats at q 0.9 and 1.0 with X
    independent, and at q 1.0 with X mildly clustered; X repeats at q 1.0 with C independent) and the
    shared-effect model, each at a common firing rate of 0.04 and 0.10, with D_X at 0.80 and 0.90.
    The worst cell is 0.0260 at 10/3; at 3 and at 8/3 it is 0.0675, and at 7/3 0.0895 (§9.2).
  - **One minimum for both arms, not a separate one for H.** The reviewer offered a separate minimum
    for H. It was not taken: what matters is whether an arm repeats its *policy* (class and harm),
    not its bytes, and T at 0.7 may repeat its policy as readily as C and H do; nothing measures that
    before the run. When both arms repeat, 8/3 gives 0.0665–0.0675 whichever arm is X (§9.2). The
    cost is power: at (0.80, 0.25) the rule now recommends about half the time in the Beta
    scenarios, against about two thirds at 8/3 (§9.3).
  - **The round-1 count stays as a descriptive figure,** labelled breadth (last bullet below).
- **Why the harmful condition is a cap on firing draws.** Distinct draws whose step does not fire
  cannot qualify at the source (0 did in Phase 23, `PHASE23_RESULTS.md`), so they are inert for
  yield, and letting them into the denominator diluted round 0's share (Review log). A harmful
  firing policy is the costly kind: it would qualify, then fail validation. The store's rate is 3 of
  9 (0.33); the cap of one half refuses an arm whose firing proposals are more often harmful than
  not. A contrast of harmful draws per planned draw (X minus C ≤ 0.10) was implemented first in
  round 1 and dropped before any data, because under the store's harm model it refused 33–79% of
  arms that fire at 0.25–0.40, the arms that help most
  (`artifacts/phase25-2026-09-24/review-r1/dropped-harm-contrast/`).
- **Why the working condition is there at all:** a distinct policy without a step that fires does
  not raise yield. In Phase 23, 0 candidates qualified at the source without the step
  (`PHASE23_RESULTS.md`, the funnel).
- **Descriptive beside the decision (never inputs):** the draw-level worst-case working rates W_X
  and W_C, the harmful draws per planned draw of X and of C, the harmful share of all distinct
  draws, the prompts whose share favours X and those that favour C with an exact sign test on them,
  and round 1's breadth count (eligible prompts where X has a WORKING draw and C has no
  WORKING-or-missing draw, minus the reverse).

### 8.3 Mechanism read-out (C against H)

**`COPYING_OF_THE_PRIOR_TEXT_SHOWN`** only if all hold (rates over received draws):
- C and H are complete (`complete`);
- dup_C − dup_H ≥ 0.30, where dup is DUPLICATE draws / received draws (`duplicate_drop_at_least_0.30`);
- one-sided exact sign test over prompts on each prompt's duplicate mean, C above H: p < 0.05
  (`sign_test_p_below_0.05`);
- distinct_H − distinct_C ≥ 0.30 (`distinct_gain_at_least_0.30`);
- H's (`INVALID` + `STALE_PARENT` + `NO_CHANGE`) share ≤ C's + 0.10 (`non_candidate_at_most_C_plus_0.10`).

The last two are new in round 1: without them, H could "show copying" by returning `NO_CHANGE` or
invalid output wherever C duplicates, with no distinct policy gained (Review log). Otherwise the
read-out is **`NOT_SHOWN`**, or **`INCOMPLETE`** if C or H is incomplete (then §8.6 applies). It is
always quoted beside **N's rate of writing slot 1's policy** with its Wilson interval. T's duplicate
rate and its sign test against C are descriptive.

### 8.4 Descriptive only (never a decision input)

- Per arm: class counts; distinct, duplicate, byte-identical-to-slot-1 and rules-text-identical
  rates; invalid and `NO_CHANGE` counts; distinct firing, distinct firing and harmful, and working
  counts; working draws on the 2 prompts whose slot-1 policy fires; step present and dead steps
  among distinct draws; every side-rule flag; distinct and working policy counts. Wilson 95%
  intervals over received draws; they understate uncertainty because draws cluster by prompt.
- **How each arm's draws arrived:** draws received on the blind retry, draws received on the
  re-send, requests re-sent, `REQUEST_TIMEOUT` attempts, draws missing after every attempt, and
  requests never attempted. A 20 s timeout could cut off long outputs, and length may differ by arm;
  these counts show whether that happened.
- Per contrast: Newcombe 95% intervals for the distinct and working differences (received draws);
  the sign test on working draws; the distinct sign test with prompts collapsed by slot-1 policy
  (22 clusters); the draw-level working and harmful rates of §8.2.
- **Determinism** (C and H, 3 repeats each): byte-identical and same-policy repeat pairs, and
  prompts whose three repeats are all byte-identical. **C only** is compared with the historical
  output of the same stored request (byte and policy), by the read-outs, from the saved raw text. No
  live line carries this comparison (review round 2, §8.6). T, H and N send other requests, so they
  have no historical output of their own and none is compared.
- The served `model` and `system_fingerprint` of every response (recorded, never enforced),
  measured tokens, statuses, attempts, waits, the re-send pass, the stop reason, and how the run
  ended (`run_end` in `readouts.json`: status, stop reason, any stop signal and where it arrived,
  and whether the round-1 fallback was permitted and why).
- By construction H cannot copy slot 1's layout from its input, so its rules-text-identical rate
  is expected near 0 and says nothing about the mechanism (pitfall 72). The mechanism read-out
  uses the policy hash only.

### 8.5 Decision table and what adoption would take

| T (declared) | H (declared) | statement recorded (`readouts.json` `statement`) |
|---|---|---|
| RECOMMEND | not RECOMMEND | "recommended for a later loop's own declaration: T" |
| not RECOMMEND | RECOMMEND | "recommended for a later loop's own declaration: H" |
| RECOMMEND | RECOMMEND | "… : T, H". This phase prefers neither; their combination was not tested |
| neither | | "no arm is recommended: T <decision> (<failed conditions>); H <decision> (<failed conditions>)" |

A declared decision that came from the round-1 fallback carries " (round 1 only)" after the arm or
decision. The mechanism decision (with its basis), dup_C, dup_H and N's rate are reported beside
the statement in every case.

- **Recommended is not adopted.** A later loop may declare the change. It is never used in a run
  compared with earlier phases unless that run declares it.
- **Adoption changes `backend/app`,** so it needs a new configuration, a new freeze and its own
  review:
  - T needs a per-role (or per-slot) Mechanic temperature; `MODEL_REQUEST_SETTINGS` in
    `runtime.py` is global;
  - H needs `completion_study.py` to build `candidate_history` without `raw_outputs`.
- **The result transfers only to the same intervention.** The later loop's slot-2 request must be
  byte-identical to this probe's arm request on these 26 prompts. That is a $0 check reusing this
  harness's rebuild; if it fails, this phase's result does not apply.
- Nothing here touches `assess_pairs`, C1–C8 or any threshold. Nothing is called ACCEPTED,
  certified or promoted.

### 8.6 Round-1 fallback (declared now, used only when a decision is INCOMPLETE after a stop the operator does not choose)

- **When:** an arm's all-rounds decision (§8.2) is `INCOMPLETE`, or the mechanism read-out is,
  **and** the run ended by a stop the operator does not choose, with no stop signal recorded:
  - the run completed (an arm can still be short of 75 after errors and the re-send pass), or it
    stopped at the spend guard or at five errored requests in a row (`completed`, `spend_guard`,
    `consecutive_errors`); or
  - it crashed and the harness recorded the traceback (`ABORTED` with a traceback, for example a
    request digest mismatch).
- **Never after an operator stop** (review round 2). These leave an `INCOMPLETE` decision
  `INCOMPLETE`:
  - SIGINT or SIGTERM at any time, **whoever sent it** (review round 3). The handler cannot tell who
    sent a signal, so a SIGTERM from the OS (a restart for an automatic macOS update, a logout, a
    shutdown) or from a tool that launched the run and cleans up its process group counts exactly as
    the operator's own `kill -TERM`: it forfeits the round-1 fallback. §12 step 6 lists the checks
    that keep such a stop from happening. The first signal is recorded in the manifest as
    `stop_signal`: the signal, when it arrived, the request in flight, the last request recorded, and
    the requests and re-sends done; later signals are only counted (`stop_signals_received`);
  - an operator stop of the re-send pass;
  - a process that died with no final manifest and was closed with `--finalize-abandoned`
    (`abandoned`). This is declared an operator stop whatever killed it (`kill -9`, a power loss),
    because the record cannot tell them apart.
- **What:** the same rule applied to round 1 alone (repeat 0: 26 planned draws per arm; complete at
  25 of 26), with the working-share minimum **4** instead of 10/3 (chosen the same way for one draw
  per prompt; §9.2). With one draw per prompt, a prompt's share is 0 or 1, so the round-1 gain is a
  count of prompts. The mechanism read-out uses round-1 C and round-1 H (26 planned draws each) and
  the same thresholds.
- **Its result is the declared decision,** labelled `round_1_only` in `readouts.json`
  (`declared.basis`) and "(round 1 only)" in the statement. The all-rounds decision is reported as
  `INCOMPLETE` beside it, with every all-rounds figure computed on what arrived. When the
  all-rounds decision is not `INCOMPLETE`, no fallback is computed. `readouts.json` records
  `run_end.round1_fallback_permitted` and its reason.
- **`PHASE25_RESULTS.md` must quote the all-rounds partial contrast beside any round-1 decision:**
  D_X, D_C, the working-share gain, the invalid and harmful figures and the sign test, as computed on
  the draws that arrived, and the stop reason with any `stop_signal`.
- **Why:** without a fallback, any stop after about `r0104` and before `r0249` spends $5–12 and
  leaves no answer, and §10 forbids a second run. A continuation run was rejected: the requests it
  sent would be re-drawn after their block partners were seen. Round 1's version applied the
  fallback after any stop. Review round 2 showed that this let anyone watching the run choose the
  rule: stop after `r0104` when round 1 alone recommends, otherwise let the run finish. Under the
  yield null that raised P(`RECOMMEND`) 1.7 to 3.3 times (for example 0.0213 to 0.0377 in the
  independent cell at w 0.10, D_X 0.80), though each arm stayed under 0.05. An operator stop can
  no longer produce a recommendation. At most it turns a result into `INCOMPLETE`, and the results
  report it as a stop, with `stop_signal`.
- **No classification is written while the run is live** (review round 2). A saved response line
  carries its status, raw text, attempts, tokens and served model, but no class, policy hash, raw
  sha256 or match with the historical output. The read-outs classify the saved raw text after the
  run. The raw text is still on disk, so this removes the easy read, not the possibility; the next
  rule still applies.
- **`--readouts` refuses until the run has ended** (review round 3). Round 2 left it accepting a run
  whose manifest was still `RUNNING`, and it then printed every arm's classes and each condition on
  the draws so far. It now refuses unless the manifest is final (`COMPLETED`, `STOPPED` or `ABORTED`,
  with an end time), with or without `--not-the-runs-harness`. A run whose process died is closed first
  with `--finalize-abandoned`.
- **The operator does not open `responses.jsonl` and does not run `--readouts` before the run has
  ended, and does not cause a stop** (for example by cutting the network to reach five errored
  requests). A stop that cannot be shown to be the operator's is the only kind that permits the
  fallback, so the rule rests on this.

## 9. Boundaries, false alarms and power (computed, $0)

From `protocol-numbers/protocol_numbers-r3.out.json`, computed by
`scripts/experiments/slot2_protocol_numbers.py` with the harness's own `contrast`,
`mechanism_readout`, `simulated_draw`, `sign_test_greater` and thresholds. 2,000 simulations per
power cell (standard error at most 0.011) and 4,000 per yield-null cell (about 0.0035 near 0.05).
The models are stated in the script and summarised here. Round 2 recomputed every figure in this
section for the working-share condition (§8.2) and three more clustering scenarios. Round 3
recomputed them again (seed `-r3`) with six **repeat scenarios** and the minimum of 10/3: an arm at
temperature 0 may return the same output for the same input, so each prompt's first draw is drawn
at the arm's rates and each later repeat is a copy of it (its class, WORKING and harm included) with
probability q, else an independent draw.

### 9.1 Count boundaries at full receipt

| condition | all rounds (78 draws per arm, 26 prompts) | round-1 fallback (26 draws per arm) |
|---|---|---|
| complete | 75 of 78 received | 25 of 26 |
| D_X ≥ 0.70 | X distinct in **at least 55** | at least 19 |
| D_X − D_C ≥ 0.30 | X distinct in **at least 24 more** draws than C's distinct plus missing | at least 8 more |
| working share | a gain of **at least 10/3**: X at least **10 more** WORKING draws than C's WORKING-or-missing draws, over the 72 draws of the 24 eligible prompts; when every repeat copies its prompt's first draw, the gain is a whole number and this means at least 4 more prompts | a gain of at least 4: at least 4 more eligible prompts with a WORKING draw |
| invalid margin | at full receipt, X at most **7** more invalid draws than C | at most 2 more |
| harmful share of firing ≤ 0.50 | at most half of X's distinct firing draws: e.g. 1 of 3, 3 of 6, 4 of 9, 6 of 12, 10 of 20 | the same |
| mechanism | at full receipt, H at least **24** fewer duplicates and 24 more distinct draws than C, and at most 7 more non-candidate draws | 8, 8 and 2 |

**The sign test needs** (untied prompts → fewest favouring X, with its p): 26 → 18 (0.038); 20 →
15 (0.021); 15 → 12 (0.018); 10 → 9 (0.011); 5 → 5 (0.031). With fewer than 5 untied prompts it
cannot pass. At temperature 0 many prompts may tie (all 3 draws alike in both arms), which shrinks
the untied count.

**Two ceilings, stated so they are not read as findings afterwards:**
- **No arm can be recommended if C's re-sent distinct draws plus its missing draws exceed 54 of
  78 (0.692).** Condition 3 would then need D_X above 1. That outcome would mean the duplicates
  do not reproduce on replay, and it is reported as that.
- **Copying cannot be shown if C's duplicate rate on replay is below 0.30.**

### 9.2 False alarms

**The yield null:** X is more distinct than C, but its step fires no more often. This is the null
that matters for condition 5. P(`RECOMMEND`) by the working-share minimum, worst cell over every model
below:

| working-share minimum (all rounds) | 5/3 | 2 | 7/3 | 8/3 | 3 | **10/3** | 11/3 | 4 |
|---|---|---|---|---|---|---|---|---|
| worst cell | 0.1747 | 0.1700 | 0.0895 | 0.0675 | 0.0675 | **0.0260** | 0.0203 | 0.0203 |

| working-share minimum (round-1 fallback) | 2 | 3 | **4** | 5 |
|---|---|---|---|---|
| worst cell | 0.1845 | 0.0722 | **0.0235** | 0.0075 |

The smallest minimum with every cell at most 0.05 is **10/3** for all rounds and **4** for round 1.
These are the harness's values (`harness_minimum_is_the_chosen_one` is true for both). 8/3 and 3 have
the same worst cell, and so do 11/3 and 4: when both arms repeat at q 1.0 the gain is a whole number
(§8.2). Round 2's minimum of 8/3 is above 0.05 on this grid only in the two scenarios where both arms
repeat.

Per cell at the declared minimum of 10/3 (all rounds), P(`RECOMMEND`), C at D 0.30 in every cell; the
last column is the worst of the four at round 2's 8/3:

| model | common w 0.04, D_X 0.80 | w 0.04, D_X 0.90 | w 0.10, D_X 0.80 | w 0.10, D_X 0.90 | worst at 8/3 |
|---|---|---|---|---|---|
| independent (ρ_C 0, ρ_X 0; the builder's model) | 0.0000 | 0.0000 | 0.0005 | 0.0000 | 0.0063 |
| T-like (ρ_C 0.5, ρ_X 0.2) | 0.0000 | 0.0000 | 0.0027 | 0.0030 | 0.0158 |
| H-like (ρ_C 0.8, ρ_X 0.8) | 0.0008 | 0.0013 | 0.0127 | 0.0103 | 0.0350 |
| C clustered, X not (ρ_C 0.8, ρ_X 0.0; round 2) | 0.0000 | 0.0000 | 0.0027 | 0.0018 | 0.0123 |
| C clustered, X mildly (ρ_C 0.8, ρ_X 0.2; round 2) | 0.0000 | 0.0003 | 0.0020 | 0.0045 | 0.0163 |
| X clustered, C not (ρ_C 0.0, ρ_X 0.8; round 2) | 0.0010 | 0.0005 | 0.0077 | 0.0092 | 0.0248 |
| both arms repeat (q 0.9; round 3) | 0.0037 | 0.0022 | 0.0232 | **0.0260** | 0.0665 |
| both arms repeat (q 1.0; round 3) | 0.0015 | 0.0013 | 0.0143 | 0.0203 | 0.0675 |
| C repeats (q 0.9), X not (ρ_X 0.0; round 3) | 0.0000 | 0.0000 | 0.0040 | 0.0027 | 0.0182 |
| C repeats (q 1.0), X not (ρ_X 0.0; round 3) | 0.0000 | 0.0000 | 0.0047 | 0.0040 | 0.0275 |
| C repeats (q 1.0), X mildly (ρ_X 0.2; round 3) | 0.0000 | 0.0003 | 0.0073 | 0.0090 | 0.0323 |
| X repeats (q 1.0), C not (ρ_C 0.0; round 3) | 0.0035 | 0.0037 | 0.0198 | 0.0210 | 0.0467 |
| shared firing propensity (ρ 0.0) | 0.0000 | 0.0000 | 0.0013 | 0.0003 | 0.0057 |
| shared firing propensity (ρ 0.5) | 0.0000 | 0.0000 | 0.0003 | 0.0000 | 0.0018 |
| shared firing propensity (ρ 0.8) | 0.0000 | 0.0000 | 0.0000 | 0.0003 | 0.0015 |

- **The share is neutral to clustering and to repeats; round 1's count was not.** Under the yield null
  the mean share gain is between −0.034 and +0.026 in every cell. In the same simulations, round 1's
  prompt count has a mean gain of +0.13 to +0.40 prompts in the T-like cells, +0.45 to +1.58 where C
  clusters and X does not or mildly, +1.03 to +2.90 where C repeats and X does not or mildly, and −0.69
  to −1.74 where X clusters and C does not (−1.23 to −2.92 where X repeats). At its old minimum of 6,
  its worst cell on this grid is 0.127 (C repeats at q 1.0, X not, w 0.10, D_X 0.90).
- **The worst cells are those where both arms repeat** (w 0.10): a prompt then adds 0 or 1, or
  nearly, so the sum moves in whole steps and varies more.
- **Why round 2's grid missed them.** Its Beta model draws each draw's class and harm independently,
  however large ρ is, so WORKING never clusters fully within a prompt. The round-3 reviewer's runs at
  8/3 stayed at or below 0.046 with Beta ρ 0.9–0.99 and reached 0.055–0.069 with the repeat model at
  q 0.9–1.0 (`review-r3/reviewer-evidence/`). On this grid, at 8/3, every Beta and shared cell is at
  most 0.0350 (H-like); the repeat scenarios reach 0.0675.
- **Outside the grid** (common firing 0.15 and 0.20; reported, not chosen on), P(`RECOMMEND`) at 10/3
  is at most 0.0777 (both arms repeat at q 0.9, w 0.20, D_X 0.90). It is above 0.05 in 9 of the 60
  cells: where both arms repeat (0.0537 at q 0.9, w 0.15, D_X 0.90, and 0.062–0.078 at w 0.20), where
  X repeats and C does not (0.053–0.057 at w 0.20), and in the H-like cells at w 0.20 (0.050–0.051).
  Every other cell is at most 0.0495. A common firing rate of 0.15 is about four times the historical
  C rate (1 of 26 first attempts fires), so the grid covers the null this probe expects. The round-1
  fallback's worst cell outside the grid is 0.0735.
- **The identical-arm null only** (X drawn exactly like C): P(`RECOMMEND`) is 0.000 at C = (D 0.30,
  w 0.04) and at most 0.001 at C = (D 0.50, w 0.10) in every scenario of §9.3. There the absolute
  floors (D_X ≥ 0.70, gain ≥ 0.30) make a recommendation nearly impossible by construction, so this
  figure says little; the yield null above is the one to quote. (Round 0 quoted "at most 0.1%" as if
  it were the false-alarm rate; Review log.)
- **Two arms are tested.** Under these models the family-wise false-recommendation rate under the
  yield null is at most about 0.052 (twice the worst cell at the declared minimum, 0.0260), and at
  most about 0.018 (twice 0.0090) in the scenarios closest to T against C when T does not repeat its
  policy (T-like, C clustered, C repeats); if T repeats too, the both-arms figure applies. Round 2
  quoted "at most about 0.077" (twice 0.0387) from a grid without repeats; on this grid its minimum of
  8/3 gives about 0.135 (twice 0.0675), and round 1's count at 6 about 0.25 (twice 0.127).
- **Mechanism:** with H drawn exactly like C (dup 0.66), P(`SHOWN`) is 0.000, 0.001 and 0.004 at
  within-prompt correlation 0, 0.5 and 0.8, and 0.009 when both arms repeat at q 1.0 (0.006–0.010 for
  the round-1 fallback).
- **An operator stop no longer adds to these rates.** Round 1's fallback applied after any stop;
  stopping after `r0104` whenever round 1 alone recommends raised them 1.7 to 3.3 times (Review log,
  round 2, G2). Now an operator stop leaves `INCOMPLETE` (§8.6).

### 9.3 Power of the recommendation rule

**Model.** 26 prompts × 3 draws, every draw received; 3% invalid in both arms; per-prompt
distinct and firing probabilities drawn from Beta distributions with within-prompt correlation ρ,
independently in C and X (the conservative end for the paired test); **harm at the store's rates**
(a firing draw is harmful with probability 3/9, a distinct non-firing draw with 1/26), so WORKING is
about two thirds of the firing rate w; 2 of the 26 prompts have a slot-1 policy that fires. C at D
0.30 and w 0.04 matches the historical first attempts (7 of 26 distinct, 1 of 26 firing). Twelve
scenarios. Six Beta scenarios (ρ_C, ρ_X): independent (0, 0), the builder's model, whose
`dry-plan-r3/power.json` is reproduced exactly by the same code; T-like (0.5, 0.2); H-like (0.8, 0.8);
and, from round 2, C clustered with X not (0.8, 0.0), C clustered with X mildly (0.8, 0.2), and X
clustered with C not (0.0, 0.8). Six repeat scenarios from round 3 (§9 above): both arms repeat at q
0.9 and at q 1.0; C repeats at q 0.9 and 1.0 with X independent, and at q 1.0 with X at ρ 0.2; X
repeats at q 1.0 with C independent. All at the declared minimum of 10/3.

| C: D, w | X: D, w | independent | T-like | H-like | C 0.8, X 0.0 | C 0.8, X 0.2 | C 0.0, X 0.8 |
|---|---|---|---|---|---|---|---|
| 0.30, 0.04 | 0.30, 0.04 (no effect) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.50, 0.10 | 0.50, 0.10 (no effect) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.30, 0.04 | 0.60, 0.10 | 0.001 | 0.003 | 0.009 | 0.001 | 0.002 | 0.007 |
| 0.30, 0.04 | 0.70, 0.10 | 0.006 | 0.007 | 0.019 | 0.002 | 0.011 | 0.021 |
| 0.30, 0.04 | 0.80, 0.10 | 0.006 | 0.013 | 0.034 | 0.009 | 0.015 | 0.029 |
| 0.30, 0.04 | 0.80, 0.15 | 0.086 | 0.087 | 0.138 | 0.090 | 0.098 | 0.127 |
| 0.30, 0.04 | 0.80, 0.25 | 0.531 | 0.554 | 0.500 | 0.547 | 0.523 | 0.499 |
| 0.30, 0.04 | 0.90, 0.25 | 0.555 | 0.553 | 0.528 | 0.567 | 0.561 | 0.522 |
| 0.30, 0.04 | 0.80, 0.35 | 0.883 | 0.846 | 0.767 | 0.855 | 0.825 | 0.768 |
| 0.30, 0.04 | 0.90, 0.40 | 0.959 | 0.948 | 0.913 | 0.951 | 0.948 | 0.913 |
| 0.50, 0.04 | 0.90, 0.25 | 0.542 | 0.499 | 0.468 | 0.475 | 0.466 | 0.478 |

| C: D, w | X: D, w | both repeat, q 0.9 | both repeat, q 1.0 | C q 0.9, X ρ 0 | C q 1.0, X ρ 0 | C q 1.0, X ρ 0.2 | X q 1.0, C ρ 0 |
|---|---|---|---|---|---|---|---|
| 0.30, 0.04 | 0.30, 0.04 (no effect) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.50, 0.10 | 0.50, 0.10 (no effect) | 0.001 | 0.001 | 0.000 | 0.000 | 0.000 | 0.000 |
| 0.30, 0.04 | 0.60, 0.10 | 0.014 | 0.009 | 0.002 | 0.001 | 0.004 | 0.016 |
| 0.30, 0.04 | 0.70, 0.10 | 0.033 | 0.029 | 0.007 | 0.009 | 0.011 | 0.034 |
| 0.30, 0.04 | 0.80, 0.10 | 0.050 | 0.045 | 0.006 | 0.011 | 0.015 | 0.056 |
| 0.30, 0.04 | 0.80, 0.15 | 0.158 | 0.135 | 0.095 | 0.099 | 0.115 | 0.167 |
| 0.30, 0.04 | 0.80, 0.25 | 0.465 | 0.379 | 0.526 | 0.528 | 0.512 | 0.465 |
| 0.30, 0.04 | 0.90, 0.25 | 0.489 | 0.452 | 0.558 | 0.573 | 0.555 | 0.506 |
| 0.30, 0.04 | 0.80, 0.35 | 0.662 | 0.625 | 0.846 | 0.816 | 0.828 | 0.691 |
| 0.30, 0.04 | 0.90, 0.40 | 0.808 | 0.793 | 0.938 | 0.941 | 0.915 | 0.805 |
| 0.50, 0.04 | 0.90, 0.25 | 0.432 | 0.383 | 0.456 | 0.418 | 0.432 | 0.445 |

- **Power is modest unless the change fires often.** w is the firing rate; WORKING is about two
  thirds of it. At X firing on 0.15 of draws (about 0.10 WORKING) the rule recommends 9–17% of the
  time; at 0.25, 38–57%; at 0.35, 63–88%. A `NOT_RECOMMENDED` at a true firing rate near 0.10–0.25 is
  likely and does not mean "no effect".
- **Condition 5 decides most misses.** At (0.80, 0.15) it fails in 82–91% of runs across the twelve
  scenarios and at (0.80, 0.25) in 43–57%, while each distinct condition fails in at most 14% at
  both.
- **Round 3's minimum costs power.** At (0.80, 0.25) the six Beta scenarios give 0.50–0.55 at 10/3,
  against 0.64–0.75 at round 2's 8/3; at (0.80, 0.15), 0.09–0.14 against 0.22–0.26. Where both arms
  repeat, the gain moves in whole prompts and power is lower still (0.38–0.47 at (0.80, 0.25)). That
  is the price of a minimum whose false-alarm rate holds when the arms repeat.
- **Against round 1's count,** the share at 10/3 has much less power at small effects without
  clustering (independent, (0.80, 0.15): 0.09 against 0.36) and about the same under clustering
  (H-like, (0.80, 0.25): 0.50 against 0.48), but it keeps its false-alarm rate where round 1's count
  does not (§9.2).
- **The harmful cap:** under the store's rate (one third of firing policies harmful) it fails in
  2–23% of runs across these alternatives (5–15% at (0.80, 0.25)), most at low firing rates, where
  there are few firing draws.
- **At D_X 0.70 the rule passes rarely** (at most 3.4% at w 0.10): 0.70 is the floor itself.
- **Earlier power figures are withdrawn.** Round 0's counted harmful firing draws as working and 4
  draws as enough (0.91 at (0.80, 0.15)). Round 1's used the prompt count (0.36 at (0.80, 0.15)
  independent). Round 2's used 8/3 (0.22 at (0.80, 0.15) and 0.75 at (0.80, 0.25), independent; now
  0.09 and 0.53).

**Round-1 fallback** (one draw per prompt, so neither ρ nor q has any effect; working-share minimum 4,
which with one draw per prompt is a count of prompts):

| C: D, w | X: D, w | P(RECOMMEND), round 1 only |
|---|---|---|
| 0.30, 0.04 | 0.30, 0.04 | 0.000 |
| 0.50, 0.10 | 0.50, 0.10 | 0.001 |
| 0.30, 0.04 | 0.60, 0.10 | 0.011 |
| 0.30, 0.04 | 0.70, 0.10 | 0.028 |
| 0.30, 0.04 | 0.80, 0.10 | 0.043 |
| 0.30, 0.04 | 0.80, 0.15 | 0.130 |
| 0.30, 0.04 | 0.80, 0.25 | 0.397 |
| 0.30, 0.04 | 0.90, 0.25 | 0.443 |
| 0.30, 0.04 | 0.80, 0.35 | 0.633 |
| 0.30, 0.04 | 0.90, 0.40 | 0.779 |
| 0.50, 0.04 | 0.90, 0.25 | 0.373 |

The fallback's power is at the low end of the all-rounds rule's (0.40 against 0.38–0.55 at (0.80,
0.25); 0.63 against 0.63–0.88 at (0.80, 0.35)), and its harmful cap fails more often (10–19% of runs),
because one draw per prompt gives few firing draws. It exists so that a run stopped by something the
operator does not choose still answers; a "round 1 only" `NOT_RECOMMENDED` is weak evidence of no
effect.

### 9.4 Power of the mechanism read-out (C duplicating at 0.66 of draws)

| H duplicate rate | ρ 0 | ρ 0.5 | ρ 0.8 | both repeat (q 1.0) | round 1 only (ρ 0) |
|---|---|---|---|---|---|
| 0.66 (no effect) | 0.000 | 0.001 | 0.004 | 0.009 | 0.006 |
| 0.50 | 0.025 | 0.082 | 0.103 | 0.134 | 0.132 |
| 0.40 | 0.252 | 0.304 | 0.325 | 0.355 | 0.370 |
| 0.36 (a drop of exactly 0.30) | 0.438 | 0.442 | 0.450 | 0.481 | 0.467 |
| 0.30 | 0.753 | 0.684 | 0.655 | 0.658 | 0.642 |
| 0.10 | 0.999 | 0.998 | 0.991 | 0.972 | 0.963 |

A true drop of 0.30 is shown about 44–48% of the time (47% in the round-1 fallback). `NOT_SHOWN` at
a true drop of 0.2–0.3 is likely, and it does not mean "no copying". The two conditions added in
round 1 cost little here: with the same invalid rate in both arms, the distinct gain equals the
duplicate drop up to noise. (Rounds 2 and 3 changed nothing in the mechanism read-out; round 3 added
the repeat column, and the other figures moved only because the simulations were re-run with a new
seed.)

### 9.5 What the probe cannot see

- whether a distinct step policy qualifies at the source gate or survives validation (no
  episodes run);
- any harm outside the two declared side-rule patterns;
- the effect of T on slot 1 (slot 1 is not re-sent).

## 10. Bounds, spend cap, waits and stop rule

| | value |
|---|---|
| planned requests | **260** (78 distinct prompts) |
| per-request bound | **$0.04984** |
| planned bound | **$12.96** |
| hard spend cap | **$15.00 for the whole phase**: 300 attempts, leaving **40 for blind retries and re-sends** |
| token-priced estimate | about **$5.73** (each prompt's local token count + 24, and the historical median slot-2 output, 463.5 tokens); at most **$7.31** with every output at 2,000 tokens. Unmeasured; the ledger carries the bound |
| largest input | 16,777 tokens (C and T); the runtime refuses above 32,000 |
| budget before this phase | $600.65 charged, $399.35 remaining; reconcile first if Phase 26 or 27 has spent since |

**Spend guard.**
- It charges every attempt, including a retry or a re-send, at the bound, in whole micro-dollars,
  and refuses the attempt that would pass the cap. In the main pass the run then stops with
  `spend_guard`.
- The plan is refused before any call if it cannot fit under the cap.
- **The cap is a phase cap.** A live run's cap is the smaller of `--spend-cap` and $15.00 minus the
  `charged_upper_bound` of every earlier run that delivered nothing; the manifest records
  `spend_cap`, `spend_cap_requested` and `earlier_undelivered_charged`. An undelivered run that
  stopped on 5 errored requests is charged at most 10 attempts, so the plan still fits after 4
  such runs.

**Retries.** A blind retry, at most once per request and charged: a transport failure that
delivered no generation (`CONNECTION_ERROR`, `REQUEST_TIMEOUT`), after 10 s. A delivered generation
is never re-rolled, and `EMPTY_FINAL_RESPONSE` is a received `INVALID`, never retried (pitfall 49).
The store holds 4 Mechanic transport failures (3 connection errors, 1 timeout) against 161 stored
Mechanic outputs, about 2.4% per call; at that rate, independently, needing more than 40 retries in
260 requests has probability below 10⁻²⁰. Outages are not independent, which is what the waits, the
re-send pass and the stop rule are for.

**Re-send pass (new in round 1).** Only if the main pass attempted every planned request: each
request whose every attempt failed with `CONNECTION_ERROR`, `REQUEST_TIMEOUT`, `HTTP_ERROR` or
`PROVIDER_ERROR` and that shows no sign of a delivered generation is re-sent **once**, in plan
order, under the same blind retry, waits and consecutive-error rule, charged. Nothing was observed
for such a request, so re-sending it is blind (pitfall 49), not resampling. A delivered generation
(even an `INVALID_RESPONSE_SHAPE`), a local refusal (`INPUT_LIMIT`, `SECRET_INPUT` and the like) and a
request mismatch are never re-sent. The re-send line is marked `"resend": true`; the manifest
records `resend_pass` (eligible, sent, received, how it ended). The re-send happens after the rest of
the run, so its draw is not back to back with its block partners; the per-arm re-send counts show
how many draws that affects. Without it, two short outage bursts (each 4 errored requests in a row,
one short of the stop, so 1–2 draws per arm each) can remove 4 draws from an arm, which tolerates
only 3 missing.

**Waits.** After a request that ends in error (after its retry, if any), the harness waits 30 s, 2
min, 5 min, then 5 min for the first to fourth errored request in a row. A received response resets
the count. Waiting is not resampling.

**Request digest.** Before every send, the client wrapper checks that the runtime built the frozen
temperature, applies the arm's temperature, and recomputes `content_hash` of the exact `create()`
keywords (`model`, `messages`, `max_tokens`, `response_format`, `temperature`, `stream`,
`extra_body`). It forwards the request only if that equals the planned `request_hash`. A mismatch
is never sent: it is recorded and the run aborts.

**Every paid response is saved first.** Each response line (status, raw text, attempts, served
metadata) is written and fsynced before the manifest that counts it. Since review round 2 the live
loop runs no classifier at all: a line carries no class, policy hash, raw sha256 or historical
match (§8.6), so nothing that can raise runs before the line is saved, and a classifier fault can
never lose a paid response (round 0 could; Review log). The read-outs classify the saved raw text
after the run.

**Stop rule.** The run stops at the first of:

| stop | recorded as |
|---|---|
| all 260 requests attempted (and the re-send pass run or cut short; its end is in `resend_pass`) | `COMPLETED` / `completed` |
| the spend guard in the main pass | `STOPPED` / `spend_guard` |
| a 5th errored request in a row in the main pass (after about 12.5 minutes of waiting) | `STOPPED` / `consecutive_errors` |
| SIGINT or SIGTERM from anyone (the operator, the OS, a launching tool), after the request in flight (a wait is cut short); the first signal is recorded as `stop_signal` (§8.6) | `STOPPED` / `operator_stop` |
| another paid run seen by the re-check right after the claim; nothing is sent, $0 | `ABORTED` / `another_paid_run_after_claim` |
| a request digest mismatch, or any other exception (traceback scrubbed of keys) | `ABORTED` |
| the process dies with no final manifest, closed afterwards at $0 by `--finalize-abandoned` | `ABORTED` / `abandoned` |

- After any stop, the read-outs are computed on whatever arrived. An arm below its all-rounds
  completeness bound falls back to round 1 only after a stop the operator does not choose (§8.6);
  after an operator stop, or below its round-1 bound, it is `INCOMPLETE`.
- **No resume, and one run that delivers anything.** Each run needs a new directory, exactly
  `artifacts/phase25-<date>/<name>`. An earlier run that is not final, or that delivered any
  generation, refuses every later run; a second draw would be repeat-until-lucky and needs its own
  declared phase. Claims are matched to manifests by the directory each claim names.
- **Atomic claim.** Each live run takes `artifacts/phase25-live-claims/claim-NN.json` (written in
  full, then hard-linked to its name; never deleted) after its last offline check. The first
  manifest (`STARTING`, with the `pid`) is written right after the claim; then the check for other
  paid runs runs once more (it cannot see this run's own claim); then `plan.json` and
  `prompts.jsonl`, then `RUNNING`. No provider call is made before `RUNNING`.
- **A dead claim** is closed at $0 with `--finalize-abandoned artifacts/phase25-live-claims/claim-NN.json`.
  It refuses while the claim's process may be alive and for a final run; it charges every recorded
  attempt plus 2 unrecorded in-flight attempts if the run died while `RUNNING`. A later run is
  allowed only if nothing was delivered.
- **Progressive records:** `slot2-probe-manifest.json` is rewritten after every request, and
  `responses.jsonl` is appended and fsynced per request.

## 11. One paid run at a time, and the live gate

**The harness refuses to launch** while any of these hold. It checks them before building the
plan, again at the start of the live path, again after the credential read, and once more right
after the claim (a sibling runner that passed its own guard before this claim existed is caught
there; this run then ends at $0):
- a Phase 20 (`phase20-*/*/dev-probe-manifest.json`) or Phase 21 (`phase21-*/*/lapse-probe-manifest.json`)
  manifest, or the Phase 23 manifest, is not final;
- any `*manifest*.json` at run depth under `phase26-*` to `phase29-*` is not final (those phases
  are being built beside this one and their manifest names are not known here);
- a claim in `phase21-live-claims` or `phase26-live-claims` to `phase29-live-claims` names a
  directory with no final manifest, **or names anything other than exactly
  `artifacts/phase2N-<x>/<name>`** (never `phase22-*`, a claims directory, `.` or `..`). Such a claim
  is a blocker and nothing it names is read;
- **another process was launched as a paid experiment run,** from a read-only `ps` listing, matched by
  tokens, not substrings (review round 2), widened in the fail-closed direction in review round 3: the
  command line's first token is a Python executable (any name that starts with `python`, in any case,
  so `python3.13t`, `python3.12-intel64` and macOS's framework `Python` count); the script it runs (its
  first argument after Python's own options, including the separate values of `-W`, `-X` and
  `--check-hash-based-pycs`; `-c`, `-m` and `-` are not a script run) is any path ending in
  `experiments/<name>.py` (so a runner started from `scripts/` as `experiments/x.py` counts); and a later
  token is `--execute-live` or any prefix of it from `--e` up (argparse accepts every unambiguous prefix,
  and six older runners have no other `--e…` option, so `--e` and `--ex` launch them live). A command
  line `shlex` cannot parse is split on whitespace. A shell, `grep` or heredoc that merely mentions
  those words is not a run. Still not seen: a runner started by its bare name from inside
  `scripts/experiments/` (`python x.py --execute-live`; round 1 did not see it either). Every runbook
  launches from the repository root. This process, its ancestors and its **descendants** are excluded:
  `caffeinate -is <python ...>` keeps the original pid for Python and forks the caffeinate helper as
  Python's child, with the launch arguments on its command line (measured; `review-r2/process-tree/`).
  Another run launched the same way is still caught through its Python process. If the process list
  cannot be read, that is itself a blocker. This also sees runners whose artifacts this guard does
  not glob (for example a Phase 17-style full loop). The refusal says what clears each kind of
  blocker; `--ignore-manifest` clears only a manifest or a claim, never a process;
- a read-only `GET http://127.0.0.1:8000/api/config/status` reports an `active_campaign_id`, or
  cannot be read. A refused connection means the backend is down, so no backend-driven run can be
  active.

Globs use exact depths; nothing under `phase22-*` (the heldout-2 seal) is listed, and a file named
`heldout-manifest.json` is skipped wherever manifests are read, including in a claimed directory.
A crashed run can be named with `--ignore-manifest <exact path>`, which the manifest records.

**The live gate.** The harness calls the provider only if all of these hold:
- `--execute-live`, `--out`, `--confirm-entity`, `--expect-plan-hash`, `--expect-harness-sha256` and
  `--expect-protocol-sha256` are all given;
- the output directory is new and exactly `artifacts/phase25-<date>/<name>`; every earlier live run
  is final and delivered nothing;
- no other paid run is in progress (above);
- the harness sha256 matches;
- this file exists and its sha256 matches `--expect-protocol-sha256`;
- the recomputed plan hash matches, and this file contains the harness sha256 and the plan hash;
- **the review is enforced, not only procedural:**
  - this file's opening status block (everything before its first `## ` heading) no longer carries
    the harness's case-sensitive `REVIEW_PENDING_MARKER` phrase;
  - this file has a bare line (no backticks, list marker, bold or table) reading exactly
    `Reviewed for launch: harness <sha256> plan <hash>` with the two pins;
  - `artifacts/phase25-2026-09-24/review.json` names this file's sha256 as `protocol_sha256`, and the
    same `harness_sha256` and `plan_hash`. Any edit to this file after the record is written makes
    the gate refuse;
- every planned request has a verified prompt whose hash and request digest match the plan;
- the run's cap (§10) is positive and the plan fits under it;
- after the only credential read: the entity matches `--confirm-entity`, the project is
  `shreetbohara-quinstreet/Faultlab`, the configuration pins hold, and the Mechanic role resolves to
  `deepseek-ai/DeepSeek-V4-Pro-0813`;
- the stop handlers are installed; a stop that has already arrived refuses before the claim;
- the atomic claim is taken, and the list of earlier runs is unchanged since the offline checks.

**Tests.** A test covers each refusal above and each stop. Round 1 added tests for the ones round 0
had left untested (round 0's line "A test covers each refusal" was false; Review log R2). Round 1's
line "39 of 39 killed" was true of its mutants, but it overstated coverage of the new process-list
refusal: an autouse fixture made the process list empty in every test, so the link from the real
`ps` listing into all four checks, the check right after the claim, the consecutive-error stop in
the re-send pass and the mechanism fallback's use of round-1 C could each be removed with all 62
tests passing (Review log, round 2, G3). Round 2 added a test for each: the real process list feeding
`other_paid_runs` and `run_live` (refused before the claim); a paid-run process that appears only
after the claim (`ABORTED` / `another_paid_run_after_claim`, $0); a re-send pass stopped at its fifth
errored request; and the mechanism fallback's planned counts (26 and 26). It also added a test for
each sibling manifest glob and each sibling claims directory (round 1 tested the shared loop on
Phase 20, 26 and 27 only, so a mutant dropping the Phase 21 or Phase 23 glob would have survived).
The Mechanic-role refusal
can be reached only if the pin check were bypassed, because the configuration hash covers the role
models; its test bypasses the pin check to show the refusal itself. **Mutation check (round 2):**
round 1's 39 mutants (two re-pointed at the changed code), the round-2 reviewer's six (R2-A, R2-B,
R2-C, R2-E, R2-F, R2-G) and 22 on the round-2 fixes (N01–N22): **67 of 67 killed**, with the
unmutated code passing all 88 tests (`artifacts/phase25-2026-09-24/review-r2/mutation/`). Two earlier
runs each left one survivor (N01, then N20), and the tests were strengthened each time (Review log,
round 2). That count did not include the 16 mutants the round-3 reviewer then wrote, and 13 of them
survived: three that fail open (the `--exe` floor, the separate value after `-W`, the whitespace
fallback for a command line `shlex` cannot parse), the untested first-signal record, eight that only
make the guard refuse more, change refusal text, or change nothing on the real plan and process tree,
and X16 (Review log, round 3, finding 4). Round 3 added a test for each of them except X04 and X16.
**Mutation check (round 3):** the 67 above (N12 and N21 re-pointed at the widened interpreter test
and the new minimum), the round-3 reviewer's 16 (X01–X16; X01 and X02 re-pointed at the widened
constants) and 8 on the round-3 fixes (P01–P08): **89 of 91 killed**, with the unmutated code passing
all 91 tests (`artifacts/phase25-2026-09-24/review-r3/mutation/`). The two survivors are kept on
purpose. X04 (the script token searched instead of fully matched) only makes the guard refuse more.
X16 (a signal not recorded once the manifest is final) changes the record only in a window of a few
statements after the run has stopped sending; the harness keeps the stricter behaviour and records
such a signal. Mutation testing shows that the tests fail when the listed lines change; it does not show that
every behaviour is tested.

## 12. Runbook

This probe drives neither the lab backend nor the simulator. It calls W&B Inference directly from
one process. The standing pre-run checks apply as follows:

| check (origin) | here |
|---|---|
| `check_ingestion_health.py` (Phase 12) | not required: no Weave traces, no evidence verification. Harmless to run |
| `start-simulator.sh`, dashboard closed, `loop_latency.py` (Phase 19) | not applicable: no worlds and no lab requests. The only lab contact is the read-only status GET |
| "restart both services deliberately" (CLAUDE.md) | not applicable, and **do not** stop or restart :8000, :8001 or :5173. The probe runs the frozen code in its own process; the pins and the freeze check verify that code (§3) |
| configuration hash `2cf63e93…` (Phase 22) | enforced by the harness: recomputed without `.env` at plan time, and again after the credential read |
| code freeze `8994e962…` (Phase 22) | enforced in part (§3). `gate_freeze.py` is not run, because it hashes held-out and audit files this phase must not read |
| `check_clock_drift.py` afterwards (Phase 19) | not applicable: no world, no tick |
| heldout-2 (Phase 22 §7.5) | never read, listed or used |
| one paid run at a time | enforced (§11), including the process list. Also confirm by hand that no Phase 26 or 27 run is live |
| no other agent working in the repository | by hand (review round 2, G4). Another agent's shell, grep or test run no longer blocks this launch (§11), but an agent at work may edit a file the pins cover or start a run, and a sibling harness whose guard still matches substrings may refuse its own launch because of this run |
| mains power | `pmset -g batt` must show `Now drawing from 'AC Power'`; `caffeinate -s` prevents system sleep only on mains power (Phase 20 review item L9), and the worst case is about 100 minutes plus waits |
| no stop the OS or a tool sends (review round 3) | any SIGTERM is an operator stop and forfeits the round-1 fallback (§8.6), whoever sent it. `pmset -g sched` must list no shutdown, restart or sleep in the next three hours; automatic installation of macOS updates is off for the run (System Settings → General → Software Update → Automatic Updates; `defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates` prints `0`), or the operator has confirmed that no update is pending (`softwareupdate --list`, which asks Apple's server); and the run is launched from a terminal window the operator keeps open, not from an agent's or tool's shell that may clean up its process group |
| budget | reconcile `memory/context/runtime-and-evidence.md` before launch |

**Steps.**
1. **Review.** Rounds 1, 2 and 3 are done (Review log). Round 3's fixes changed the harness again
   (the working-share minimum, the process guard's token rule, `--readouts`); they have tests and a
   mutation check (§11) but no fourth review round (pitfall 74). The owner decides whether to ask for
   one before step 3.
2. **If the harness changes again,** its sha256 and the plan hash change. Then, from the repository
   root:
   - write a new dry plan to a new directory
     (`--write-plan artifacts/phase25-2026-09-24/dry-plan-r4 --power`);
   - in `scripts/experiments/slot2_protocol_numbers.py`, set `PLANNED_PLAN_HASH` to the new plan
     hash, and give `SEED` and the output file name in its docstring the new round label (`-r4`);
   - re-run it into the new output file (`protocol-numbers/protocol_numbers-r4.out.json`) and check
     `plan_hash_is_the_declared_one` and `harness_minimum_is_the_chosen_one`;
   - re-run the tests (step 5);
   - re-run the mutation check against the new harness: copy
     `artifacts/phase25-2026-09-24/review-r3/mutation/` to a scratch directory, create `tests/` there,
     run `prepare.py` then `mutate.py`, re-point any mutant reported `SKIPPED`, and save the results
     in a new `review-r4/mutation/`;
   - update §3 and every figure that moved.
3. **Close the review in writing** (only after the owner approves), in this order:
   - add the closing entry to the Review log;
   - replace the status block so it no longer carries the review-pending phrase (do not write that
     phrase anywhere in the status block);
   - add the bare line `Reviewed for launch: harness <sha256> plan <hash>` with the final pins, with
     nothing around it;
   - record `shasum -a 256 docs/part2/PHASE25_EXPERIMENT.md`;
   - write `artifacts/phase25-2026-09-24/review.json` with the keys Phase 21's record
     (`artifacts/phase21-2026-09-23/review.json`) uses: `phase` (the number `25`), `status`
     (`"approved"`), `approved_by` (who approved, and on whose delegation), `protocol_sha256` (that
     value), `harness_sha256`, `plan_hash`, `reviewers` (for example `"round-1: stats, safety, rules
     lenses"`, `"round-2: regressions, launch lenses"` and `"round-3: focused check of round 2's
     fixes"`) and `approved_at` (UTC, ISO 8601). The gate compares only the three hashes; the other
     keys are the owner-approval part of the record. Do not edit this file afterwards.
4. **Re-check the dry plan at $0,** from the repository root:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   ./.venv/bin/python scripts/experiments/slot2_probe.py
   ```
   It must print the plan hash in §3, `"slots_verified": 52` and `"passed": true`. A completion study
   added to the store since, of another configuration or after the cutoff, does not move the plan hash
   (§3).
5. **Re-run the tests** from `backend/`:
   `cd backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/experiments/test_slot2_probe.py`,
   then `cd ..` back to the repository root.
6. **Run once,** from the repository root, on mains power with the lid open. First:
   - `pmset -g batt` shows `Now drawing from 'AC Power'`;
   - `pmset -g sched` lists no shutdown, restart or sleep in the next three hours, and automatic
     installation of macOS updates is off (`defaults read /Library/Preferences/com.apple.SoftwareUpdate
     AutomaticallyInstallMacOSUpdates` prints `0`) or no update is pending (review round 3; see the
     checks table);
   - the command below is typed in a terminal window the operator keeps open until the run has ended,
     not run from an agent's or tool's shell: a tool that cleans up its process group would send the
     run a SIGTERM, which is an operator stop (§8.6);
   - no other agent is working in the repository, and no Phase 26 or 27 run is live;
   - `ps -axww -o pid=,command= | grep -- --execute-live | grep -v grep` lists nothing.

   Then:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/slot2_probe.py --execute-live \
     --confirm-entity shreetbohara-quinstreet --out artifacts/phase25-2026-09-24/live \
     --expect-plan-hash <plan hash from §3> \
     --expect-harness-sha256 <harness sha256 from §3> \
     --expect-protocol-sha256 <sha256 from step 3> \
     >> artifacts/phase25-2026-09-24/live-runner.log 2>&1 &
   ```
   - This launch shape was checked at $0 against the revised guard: Python keeps the original pid,
     the caffeinate helper is its child, and the guard excludes it (`review-r2/process-tree/`). Round
     1's guard refused this exact command (Review log, round 2, L1).
   - The claim file records the process id as `pid`. Stop the run only with `kill -TERM <pid>`; it
     takes effect after the request in flight (up to 20 s) or at once during a wait. Use `kill -9`
     only if SIGTERM has been ignored for more than a minute, then close the claim with
     `--finalize-abandoned`. **Either kind of stop is an operator stop:** an incomplete decision then
     stays `INCOMPLETE`, with no round-1 fallback (§8.6).
   - **Do not open `responses.jsonl` and do not run `--readouts` until the run has ended, and do not
     cause a stop** (§8.6). `--readouts` refuses while the manifest is not final (review round 3).
   - The log is appended to, so a refused re-launch cannot erase an earlier traceback, and it sits
     outside `live/`, which must not exist beforehand.
   - Requests run one at a time. The worst case is 300 attempts × 20 s ≈ 100 minutes, plus up to
     40 × 10 s before blind retries; each errored request adds 30 s to 5 min of waiting.
7. **Outputs** in `live/`: `plan.json`, `prompts.jsonl`, `responses.jsonl`, `slot2-probe-manifest.json`
   and, unless the process was killed or the run ended at the after-claim check, `readouts.json`.
8. **Afterwards,** from the repository root (`--readouts` resolves its directory against the current
   directory, while `--out` and `--finalize-abandoned` resolve against the repository root):
   - recompute at $0 with `--readouts artifacts/phase25-2026-09-24/live`. It refuses until the run's
     manifest is final (after a killed process, run `--finalize-abandoned` first), and unless this
     harness and the saved plan are the run's own (`--not-the-runs-harness` prints a mismatched
     recomputation, labelled; it never lifts the first refusal). When the run ended normally, the
     recomputation must equal `readouts.json`;
   - add the manifest's `charged_upper_bound` to the ledger;
   - write `PHASE25_RESULTS.md` from `readouts.json` only, quoting every declared read-out: both arm
     decisions with their basis, failed conditions and worst-case figures, the mechanism decision
     with N beside it, the determinism read-out, the per-arm arrival counts, `run_end` (the stop
     reason, any `stop_signal`, and whether the round-1 fallback was permitted) and the descriptive
     items. **Beside any round-1 decision, quote the all-rounds partial contrast** (§8.6);
   - **if the run stopped having delivered nothing,** a new run is allowed in a new directory (for
     example `--out artifacts/phase25-2026-09-24/live-2`) under the rest of the phase cap. Record
     both runs.
   - If a claim was closed with `--finalize-abandoned`, tell the Phase 26 and 27 operators: their
     guards may read it.

## 13. What each result would and would not mean

**T `RECOMMEND_FOR_A_LATER_LOOP`.**
- **It would mean:** on these 26 stored slot-2 requests, at temperature 0.7 the Mechanic's proposal
  differs from slot 1's policy in at least 70% of draws, at least 30 points more often than a
  temperature-0 re-send, across prompts (sign test); over the 24 eligible prompts, its share of
  WORKING draws (distinct, its retry step fires after a transient failure, no declared harmful side
  rule) exceeds C's share of WORKING-or-missing draws by at least 10/3 in total, that is, at least 10
  more WORKING draws of 72; no more than 10 points more invalid output; and at most half of its
  firing proposals carry a declared harmful side rule.
- **It would not mean:**
  - a higher certification yield: no episode ran, and the source gate and validation are single-shot
    stages (pitfall 71);
  - that the new policies are safe, qualify, or pass validation;
  - anything about slot 1 at 0.7, or about the Mechanic's other prompts, which a per-role temperature
    would also change;
  - anything held-out, ACCEPTED or certified.

**H `RECOMMEND_FOR_A_LATER_LOOP`.** The same statements with "without the exact text of the prior
proposal in its input" in place of "at temperature 0.7". It would make a change to how
`completion_study.py` builds `candidate_history` a candidate for a later loop. The same "would not
mean" list applies, except that H leaves slot 1 untouched.

**A decision marked "round 1 only".** The same statement on one draw per prompt, with the round-1
thresholds (§8.6), and much less power (§9.3). It is the declared decision, not a hint. It can exist
only after a stop the operator did not choose, and it is always quoted beside the all-rounds partial
contrast (§8.6).

**`NOT_RECOMMENDED`.** It means different things by which conditions failed, and the statement lists
them:
- **distinct conditions (2–4) failed:** the change does not reliably move slot 2 off slot 1's policy
  on these prompts;
- **distinct conditions passed, working (5) failed:** more variety, but not enough more WORKING draws
  per prompt than C. That does not help yield. Power is modest even for real effects (§9.3), so it is
  not "no effect";
- **invalid (6) or harmful (7) failed:** the change breaks the output format, or more than half of
  its firing proposals carry a declared harmful side rule. The harm reading covers two patterns only;
- **C distinct above 54 of 78:** the duplicates did not reproduce on replay (§9.1); nothing can be
  recommended, and that is the finding.

**`INCOMPLETE`** (after the fallback too, or after an operator stop, which permits no fallback). No
evidence either way for that arm.

**Mechanism `COPYING_OF_THE_PRIOR_TEXT_SHOWN`.**
- **It would mean:** with everything else in the request unchanged, removing the exact text of slot
  1's proposal lowers the rate at which slot 2 returns slot 1's policy by at least 30 points, across
  prompts, and the drop comes back as distinct policies, not as outputs that are no policy. The
  exact text causes at least part of the duplicates.
- **It would not mean** that the model cannot re-derive the same policy: N shows how often the slot-2
  evidence alone leads to it.

**Mechanism `NOT_SHOWN`.** Any of: the exact text is not the mechanism; the model repeats the
canonical `content` instead, which H keeps; the drop is real but below about 0.3, where power is
about one half (§9.4); the drop came back as `NO_CHANGE` or invalid output (the failed conditions
say which); or C's duplicates did not reproduce (below 0.30, §9.1). Read with N:
- N near C's duplicate rate: the evidence alone leads back to slot 1's policy about as often as the
  prior candidate does, so re-derivation is plausible;
- N far below C: the prior candidate's presence matters, and if H is near C, its canonical form
  (which H keeps) is enough.

These readings are descriptive; N is one draw per prompt and decides nothing.

**Determinism.** How often the V4 Mechanic, at temperature 0 through this provider, answers
byte-identical input differently within one session (C and H), and how often C matches the
historical output from 2026-09-23/24. It informs how later phases read one-draw-per-slot results. It
is not a time-drift measurement.

## 14. Limits

- **Development data only,** from two runs of one configuration. Nothing here bears on held-out
  safety.
- **A replay of one proposal step.** No episode runs, so the probe cannot see qualification,
  validation or yield; it reads only what the Mechanic writes.
- **26 prompts, 3 draws each, and fewer independent prompts than that.** Draws cluster by prompt,
  and prompts that share a slot-1 policy (22 distinct slot-1 policies over 26 studies) are related.
  The sign test treats the 26 prompts as independent, so its p-values are somewhat optimistic; the
  clustered sign test beside it (22 clusters) is descriptive. Wilson and Newcombe intervals over
  draws understate the uncertainty.
- **"Distinct" is by policy hash.** A trivially different policy (one wait tick more) counts as
  distinct, most likely at temperature 0.7. Condition 5 (the working share) is the yield-relevant
  read.
- **Breadth is not yield.** A count of prompts with at least one WORKING draw among three measures
  breadth: at equal per-draw WORKING rates it favours the arm whose draws vary more within a prompt,
  and T at 0.7 against C at 0 differs in exactly that way. A loop that takes one slot-2 draw per study
  gains from the per-draw rate. That is why condition 5 sums per-prompt shares (§8.2). The prompt count
  is reported, labelled breadth, and decides nothing.
- **The harm model in the simulations is the store's** (3 of 9 firing policies harmful, 1 of 26
  non-firing), from 35 distinct v4 policies. A new arm may write harmful policies at another rate.
- **The auditor is static and narrow.** It simulates the source path and one delayed-decision path
  with the runtime's condition logic. It agreed with stored behaviour on 40 of 40 candidates (fires)
  and 6 of 6 (premature defer), all v4-era policy shapes; policies of a new shape may fall outside
  that validation. Harm outside the two declared patterns is not seen.
- **One temperature and one presentation.** T is 0.7 on slot 2 only; H removes only `raw_outputs`
  (about 660 tokens), so H is "less of the prior text", not "no prior policy". N is the
  no-prior-policy reference, one draw per prompt.
- **No format repair.** Each draw is one request, so the invalid rate is the first-attempt rate; the
  study's final rate is lower (one of the 26 historical first attempts was invalid and was repaired).
- **Provider nondeterminism and time.** Temperature 0 does not guarantee identical output. The arms
  of a prompt are sent back to back within a round, except re-sent requests (§10); drift across the
  run and since the historical requests is not controlled. The served model is recorded, not
  enforced, and a weights change behind the same model id cannot be detected.
- **The token fingerprint is a count, not a hash** (§4).
- **The dollar figures are conservative bounds.** Token-priced cost is estimated, not measured.

## 15. No tuning, no leakage, and what must not happen

- Results are written only under `artifacts/phase25-*`. They never enter a study and are never shown
  to any model.
- **The temperature (0.7), the H and N rules and every threshold are fixed now,** including the
  working-share minimums (10/3, and 4 for round 1), the rule that only a stop the operator does not
  choose permits the round-1 fallback (any SIGINT or SIGTERM, whoever sent it, is an operator stop),
  and the harmful cap (0.50). Another value or presentation chosen after seeing these results is a
  new, declared phase that reports this one beside it.
- No edit to `backend/app`, the harness, or this file after the review record is written.
- No file named `slot2-probe-manifest.json` or `claim-*.json` saved under `artifacts/` except by the
  harness (review evidence included).
- No re-run after a run that delivered anything; no resumption or continuation; no change to the
  read-outs once data exists.
- Nothing is called ACCEPTED, certified, REJECTED or promoted.
- No held-out partition or seed, promotion record or final-audit file is read. `checks.py` is never
  read by a person or agent; the configuration recompute hashes the `backend/app` tree, which includes
  it (§3).

## 16. Where the program was corrected or made exact

1. **"Verify each against its stored hash":** no Mechanic request hash exists. Replaced by the twelve
   checks of §4.
2. **"The duplicates come from copying `candidate_history`":** **a hypothesis, not confirmed.** The
   duplicates coincide with the prior candidate being in the input, and same-input determinism is
   excluded because the inputs differ. Identical rules layout does not distinguish copying from
   re-derivation: 5 of 6 independent same-policy slot-1 pairs share the layout. Arm H tests it, with
   the reference N quoted beside it (§8.3). Whether temperature 0 contributes is T's question. (Round 0 wrote "confirmed and
   narrowed"; review round 1 refuted that.)
3. **"16 of 30 studies":** Phase 23's 16 duplicates are out of the **21** studies that reached slot 2,
   not 30. The count is the same on first attempts and in final decisions. Across Phases 17 and 23 it
   is 18 of 26 first attempts and 19 of 26 final decisions.
4. **"Step that can fire … a static check of its gating condition":** implemented as an abstract
   interpreter run, which also catches rules that stop the first send and exhausted bounds. A firing
   step with a declared harmful side rule is not counted as WORKING.
5. **Arm H** withholds the exact prior text, not the whole prior candidate (§6); the no-prior-candidate
   case is the reference arm N.
6. **The census is exactly Phases 17 and 23:** no other v4 study reached slot 2.
7. **Adopting either arm needs a `backend/app` change,** so a new configuration and freeze (§8.5).

**Figures corrected from the build report** (found while writing this protocol; the code and data were
unchanged):
- the slot-2 user message grows by 15,627–20,522 bytes, not "about 16–19 KB";
- 4 of the 10 retry-mentioning duplicates use the words "adds a bounded retry of the original
  notification request", not all 10 (7 say "bounded retry");
- slot 1's raw rules lack an `only_if` in 16 of the 18 copied cases, not all;
- "Phase 23's 16 counts final results" was not a correction: Phase 23's first-attempt and final counts
  are both 16 of 21 (item 3);
- the slot-2 output differs from slot 1's in 25 of 26, not "every time";
- the one historical distinct slot-2 output whose step fires is harmful (premature defer), so the
  historical WORKING count is 0 of 26, not 1.

## 17. Evidence files (all $0)

- `artifacts/phase25-2026-09-24/dry-plan-r3/`: `plan.json`, `dry-summary.json`, `investigation.json`,
  `power.json`, `dry-run.out.txt`. (`dry-plan/`, `dry-plan-r1/` and `dry-plan-r2/` hold the superseded
  round-0, round-1 and round-2 plans.)
- `artifacts/phase25-2026-09-24/protocol-numbers/protocol_numbers-r3.out.json`: boundaries, the yield
  null and the choice of the working-share minimums (with the round-1 breadth count beside it, and
  cells outside the grid), false alarms, power under clustering and repeats (twelve scenarios), the
  round-1 fallback, mechanism power, the review's constructed cases, the harm model from the store,
  stop points, token estimate, census facts and retry arithmetic, from
  `scripts/experiments/slot2_protocol_numbers.py`. It re-derives the plan hash
  (`plan_hash_is_the_declared_one: true`), confirms the harness's minimums are the chosen ones
  (`harness_minimum_is_the_chosen_one`), and reproduces `dry-plan-r3/power.json`.
  (`protocol_numbers.out.json`, `protocol_numbers-r1.out.json` and `protocol_numbers-r2.out.json` are
  the superseded round-0, round-1 and round-2 outputs.)
- `artifacts/phase25-2026-09-24/review-r1/mutation/`: the mutation check of the revised runner
  (`prepare.py`, `mutate.py`, the final `mutation-results.txt` on the 62-test file, and
  `mutation-results-run1.txt`, the first re-run on 60 tests, which left two survivors).
- `artifacts/phase25-2026-09-24/review-r1/dropped-harm-contrast/`: the numbers from an intermediate,
  never-pinned harness whose harmful condition was a per-draw contrast; they are why that rule was
  dropped (§8.2). Not a declared read-out.
- `artifacts/phase25-2026-09-24/review-r2/mutation/`: the round-2 mutation check (`prepare.py`,
  `mutate.py`, `README.txt`, `mutation-results.txt`, and the two earlier runs that each left one
  survivor): round 1's 39 mutants (two re-pointed), the round-2 reviewer's six (one re-pointed), and
  22 on the round-2 fixes.
- `artifacts/phase25-2026-09-24/review-r2/process-tree/`: the runbook's launch shape run at $0 against
  the revised guard (`launch_shape_check.py`, `runbook_launch_shape.out.json`, `README.txt`).
- `artifacts/phase25-2026-09-24/review-r2/share-gain/`: the seeded yield-null check of the
  working-share minimums, run on the final harness before `dry-plan-r2` was written.
- `artifacts/phase25-2026-09-24/review-r2/final-checks/`: after the last edit of round 2, the step-4 dry
  run (`dry-run-step4.out.txt`, JSON-equal to `dry-plan-r2/dry-run.out.txt` apart from `written`),
  `check_pins.py` and its output (`pins.out.txt`: every pin in §3 equals its file, and the live gate
  refuses today because of the review-pending phrase), and a read-only `other_paid_runs()` listing
  (`other_paid_runs_now.out.json`: no blocker, backend idle).
- `artifacts/phase25-2026-09-24/review-r2/reviewer-evidence/`: the round-2 reviewers' own $0 evidence
  (dispersion and optional-stopping simulations, the process-tree measurements, their mutants), copied
  unchanged from the session scratchpad so that it outlives the session (pitfall 84). The Review log
  cites it by file name.
- `artifacts/phase25-2026-09-24/review-r3/mutation/`: the round-3 mutation check (`prepare.py`,
  `mutate.py`, `README.txt`, `mutation-results.txt`): 91 mutants, 89 killed, the two survivors
  explained in the README.
- `artifacts/phase25-2026-09-24/review-r3/final-checks/`: after the last edit of round 3, the step-4 dry
  run (`dry-run-step4.out.txt`), `check_pins.py` and its output (`pins.out.txt`), a read-only
  `other_paid_runs()` listing (`other_paid_runs_now.out.json`), the §12 step 6 OS-stop checks read at $0
  (`os_stop_checks_*.out.txt`), the token rule on every shape the round-3 reviewer named against round
  1's substring rule (`token_rule_r3.py`, `token_rule_r3.out.json`), and `--readouts` on a scratch run
  whose manifest is still `RUNNING` (`readouts_on_live_run_r3.py`, `readouts_on_live_run_r3.out.json`).
- `artifacts/phase25-2026-09-24/review-r3/reviewer-evidence/`: the round-3 reviewer's own $0 evidence
  (the repeat-model and Beta simulations at 8/3 and nearby minimums, the token-rule cases, `--readouts`
  on a live run, their mutants X01–X16, and their diffs of round 2's changes), copied unchanged from the
  session scratchpad (pitfall 84); `README.txt` maps each file to its finding. The fake run directory
  one of those scripts builds is not copied (it holds a file named `slot2-probe-manifest.json`, §15).

## Review log

### Review log — round 3 (2026-09-24)

One reviewer, at $0 (no provider or W&B call, no `--execute-live`, no `.env` read, `checks.py` not read,
nothing under heldout-2, promotion or audit read, no repository file edited, no service touched),
checked round 2's fixes only (pitfall 74): the harness, the tests, this protocol and the numbers script
against their pre-round-2 copies, with simulations through the harness's own `contrast()` and the
numbers script's own models. **Verdict: RUN_WITH_CHANGES.** 5 findings: 1 major, 4 minor. Every one is
applied below; none was rejected. For finding 1 the reviewer offered two routes, re-choosing the
minimum or declaring a separate one for H; the first was taken, and the disposition says why the
second was not. The fixes changed the harness, so its sha256, the plan hash, the dry plan
(`dry-plan-r3/`), the numbers (`protocol_numbers-r3.out.json`; seed `-r3`), the numbers script and the
tests (91, from 88) all moved (§3). The reviewer's "checked and sound" list (overspend and running
twice untouched by round 2; the guard not refusing its own launch; no paid data lost on interruption;
the stop record; the fallback rule; the working share's exact arithmetic and boundaries; the refusal
advice; 88 tests passing) is not repeated here. The reviewer's evidence is in
`review-r3/reviewer-evidence/`.

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | major | Round 2's working-share minimum of 8/3 let false recommendations through above the declared 0.05 under the yield null when both arms repeat their own output across the 3 repeats, the likely behaviour of two temperature-0 arms (C and H; §2.2 says the Mechanic's temperature-0 determinism is unmeasured). If every repeat copies its prompt's first draw, each prompt's share is 0 or 1, the gain is a whole number, and 8/3 acts as a count of 3 prompts, which the round-1 fallback's own table rejects. Round 2's grid could not reach this case: its Beta model draws each draw's class and harm independently, however large ρ is (ρ 0.9–0.99 stayed at or below 0.046). With each repeat a copy of the first draw with probability q, P(`RECOMMEND`) at 8/3, w 0.10, was 0.059–0.068 at q 0.9, 0.055–0.069 at q 0.96 and 0.060–0.069 at q 1.0 over three runs; at q 1.0, 7/3, 8/3 and 3 gave identical rates. On the same draws round 1's count at 6 gave at most 0.0018. The T contrast was unaffected when T does not repeat (C copied, T at ρ 0 or 0.2: worst cell 0.0325). At 10/3 the copy model's worst cell was 0.0295 (`deterministic_null.out.txt`, `copy_model_minimums.out.txt`, `deterministic_null_compare.out.txt`, `t_arm_copy_null.out.json`). | **Applied: the minimum was re-chosen, and it is the reviewer's 10/3.** The numbers script has a repeat (copy) model: each prompt's first draw at the arm's rates, each later repeat a copy of it (class, WORKING and harm included) with probability q, else an independent draw. Six scenarios are added to the yield-null grid and to the power table: both arms repeat at q 0.9 and at q 1.0; C repeats at q 0.9 and 1.0 with X at ρ 0, and at q 1.0 with X at ρ 0.2; X repeats at q 1.0 with C at ρ 0. The mechanism table also runs both arms at q 1.0. On the new grid the smallest minimum with every cell at most 0.05 is **10/3**: worst cell 0.0260 (both arms repeat at q 0.9, w 0.10, D_X 0.90). 8/3 and 3 give 0.0675 and 7/3 gives 0.0895, all where both arms repeat; every Beta and shared cell at 8/3 stays at or below 0.0350 (§9.2). The harness's minimum is now 10/3 (`harness_minimum_is_the_chosen_one` true for both); the round-1 minimum stays 4 (worst cell 0.0235), since one draw per prompt cannot repeat. **The separate minimum for H was not taken.** What matters is whether an arm repeats its *policy* (class and harm), not its bytes. T at 0.7 may repeat its policy within a prompt as readily as C and H do, and when both arms repeat, 8/3 gives 0.0665–0.0675 whichever arm is X; nothing measures this before the run. **The cost is power:** at (0.80, 0.25) the rule now recommends 0.50–0.55 of the time in the six Beta scenarios (0.64–0.75 at 8/3) and 0.38–0.55 across all twelve; at (0.80, 0.15), 0.09–0.17 (§9.3). **Step 2 of §12 was followed:** `dry-plan-r3/` (plan hash `5db5c880…`); the numbers re-run with `PLANNED_PLAN_HASH` set to it and seed `-r3` (`plan_hash_is_the_declared_one` true; `dry-plan-r3/power.json` reproduced); boundary tests at the new minimum (a gain of exactly 10/3 passes and 3 fails; with every repeat copied, 4 prompts pass and 3 fail); a mutation re-run (P01 puts 8/3 back and N21 lowers it to 3, both killed); and §3, §8.2, §9.1–§9.4, §13 and §15. The family-wise figure is now at most about 0.052 (twice 0.0260). Round 2's "at most about 0.077" was too low for its own minimum: on this grid 8/3 gives about 0.135 (twice 0.0675). |
| 2 | minor | Round 2 counted every SIGTERM as an operator stop, including one the operator did not send: a macOS restart for an automatic update, a logout, or a tool that launched the run cleaning up its process group. After such a stop an incomplete decision stays `INCOMPLETE` for good, where round 1's fallback would have answered. The runbook requires mains power, which is when macOS installs updates automatically, and nothing checked for a scheduled restart. On this machine automatic installation was on (`AutomaticallyInstallMacOSUpdates` 1) and `pmset -g sched` listed two wakes. | **Applied, as proposed.** The handler cannot tell who sent a signal, so this is a rule and a runbook check, not a harness change; the harness's docstring and comments now say the same, and its behaviour is unchanged. §8.6 says plainly that any SIGINT or SIGTERM, including one sent by the OS or by a tool that launched the run, is an operator stop and forfeits the round-1 fallback; §5 and §10's stop table say "whoever sent it" and "from anyone". §12's checks table and step 6 add: `pmset -g sched` lists no shutdown, restart or sleep in the next three hours; automatic installation of macOS updates is off for the run (`defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates` prints `0`), or the operator has confirmed that no update is pending (`softwareupdate --list`); and the command is typed in a terminal window the operator keeps open, not run from an agent's or tool's shell. **Read again at $0 after the fixes (nothing was changed):** mains power, only scheduled wakes, and automatic installation still **on** (`review-r3/final-checks/os_stop_checks_*.out.txt`). Turning it off is a system setting, left to the operator before step 6. |
| 3 | minor | Round 2's token rule was narrower than round 1's substring rule in three ways and so failed open: (a) the script token had to contain `scripts/experiments/`, so `python experiments/x.py --execute-live` started from `scripts/` was missed; (b) the interpreter had to fully match `python[0-9.]*`, so `python3.13t` and `python3.12-intel64` were missed; (c) the `--exe` floor holds only for parsers that also have `--expect-…` options, and six older live runners (`comprehension_probe`, `locate_loss_probe`, `repeatability`, `native_baseline`, `run_gate_replays`, `run_replication`) have no other `--e…` option, so argparse accepts `--ex` and `--e` for them, which neither rule saw (`token_rule_cases.out.json`). | **Applied, as proposed, in the fail-closed direction.** The script is any path ending in `experiments/<name>.py` (`(?:.*/)?experiments/[A-Za-z0-9_.-]+\.py`, fully matched: the reviewer's `(?:^\|/)experiments/…\.py` anchored at the end); the interpreter is any basename that starts with `python`, in any case (macOS's framework `Python` too); and the flag is `--execute-live` or any prefix of it from `--e` up. Also: `--check-hash-based-pycs` takes a separate value like `-W` and `-X`, and `-` (a script read from stdin) ends the scan as not a script run. The round-2 decoys stay excluded (a shell, grep, rg, a zsh heredoc, a caffeinate helper, `-m`, `-c`, an unparseable decoy) with one deliberate change: `python tests/experiments/test_slot2_probe.py --execute-live`, which round 2 listed as not a run, now counts as one (fail closed; no runbook launches a file that way). Still not seen, as in round 1: a runner started by its bare name from inside `scripts/experiments/`; every runbook launches from the repository root (§11). Every shape the reviewer named was re-checked against round 1's rule (`review-r3/final-checks/token_rule_r3.out.json`). Test: `test_the_process_guard_matches_tokens_not_substrings_and_fails_closed` (14 real shapes, 14 decoys). Mutants X01–X04, N12–N14, P02–P04. The Phase 26 and 27 harnesses are outside this phase's files and were not edited. |
| 4 | minor | Several round-2 branches could be changed with every test passing, three of them failing open: the `--exe` floor (§11 said "down to `--exe`", but only `--exec` was tested), the separate value after `-W`, and the whitespace fallback for a command line `shlex` cannot parse (the only unparseable case tested was a decoy). The first-signal-wins record in the stop handler was untested too. Of the reviewer's 16 mutants, X01, X02, X07 and X05 survived; X03, X04, X11 and X13 survived but only make the guard refuse more or change refusal text; X08, X09, X10 and X14 survived but make no difference on the real plan and process tree; X06, X12 and X15 were killed (`mut/mutation-results-r3.txt`). Round 2's "67 of 67 killed" did not include them. | **Applied, and extended to the other survivors.** The three real runs are in the test's `runs` list (`… slot2_probe.py --exe`, `python -W ignore …`, and a real launch whose command line has an unbalanced quote), with `--ex`, `--e` and `--check-hash-based-pycs` shapes beside them. A two-signal `run_live` test sends SIGINT then SIGTERM during the first request and asserts that `stop_signal` keeps SIGINT, with its in-flight request, and that `stop_signals_received` is 2 (`test_the_first_of_two_stop_signals_is_the_one_recorded`). The other survivors got tests too: `-` on stdin is not a run (X03); `ABORTED` with a stop reason that would otherwise permit the fallback does not permit it (X08); a prompt with no rows in one arm stays eligible, with share 0 for a missing X and 1 for a missing C (X09, X10); a refusal counts every blocker and carries the lab-backend advice (X11, X13); a Python grandparent carrying the launch arguments is this run (X14). **Mutation check (round 3):** 91 mutants (round 2's 67 with N12 and N21 re-pointed, the reviewer's 16 with X01 and X02 re-pointed at the widened constants, and P01–P08 on the round-3 fixes): **89 killed**, the unmutated code passing all 91 tests (`review-r3/mutation/`). Two survive on purpose. X04 (the script token searched instead of fully matched) only makes the guard refuse more; only an invented path would separate the two rules. X16 (a signal not recorded once the manifest is final) differs only in a window of a few statements after the run has stopped sending, where the harness keeps the stricter behaviour. §11 is corrected. |
| 5 | minor | Round 2 removed the class from live lines so that nothing on disk stated which arm was ahead, but the documented `--readouts` command accepted a run whose manifest was still `RUNNING` and printed every arm's classes, its distinct and working counts, and each condition on the draws so far. §8.6 forbade opening `responses.jsonl` and causing a stop, not this command; with the acknowledged network-cut residual, it kept the easy read that round 2's G2 (b) meant to remove (`readouts_on_live_run.out.json`). | **Applied, the first option.** `recompute_readouts` refuses unless the manifest is final (`COMPLETED`, `STOPPED` or `ABORTED`, with an end time), with or without `--not-the-runs-harness`; a run whose process died is closed first with `--finalize-abandoned`. §8.6 and §12 steps 6 and 8 add "do not run `--readouts` before the run has ended". `run_live` computes its own read-outs from the saved final manifest and is unaffected. Test: `test_readouts_refuse_until_the_run_has_ended` (`RUNNING`, `STARTING`, a final status with no end time, and an end time with no status all refuse, in both modes; a `STOPPED` run is read). Re-checked on a scratch run outside the repository (`review-r3/final-checks/readouts_on_live_run_r3.out.json`). Mutants P05–P07. |

**Also found while applying round 3** (no reviewer raised these; recorded so they are not lost):
- **The first attempt at this round's numbers and mutation runs was cut off** when the session was
  interrupted: the numbers output was left empty and the mutation log stopped after M10, both in the
  session scratchpad. The harness and tests had not changed (their sha256 values equal those recorded
  when the mutation base was prepared). Both were re-run in full; only the complete runs are kept.
- **Round 1's breadth count is worse on the new grid.** At its old minimum of 6 it reaches 0.127 where C
  repeats and X does not (w 0.10), against 0.0587 on round 2's grid; it stays descriptive (§9.2).
- **Outside the grid** (common firing 0.15 and 0.20, not chosen on), 10/3 is above 0.05 in 9 of 60
  cells, at most 0.0777, all where both arms repeat, X repeats, or H-like at w 0.20 (§9.2).

**Closing for round 3.** All five findings are applied. What moved: the harness (`28b998ac…`), the plan
hash (`5db5c880…`), the dry plan (`dry-plan-r3/`), the numbers (`protocol_numbers-r3.out.json`; seed
`-r3`), the numbers script, and the tests (91, from 88). The status block still carries the
review-pending phrase, the "Reviewed for launch" line is absent, and no `review.json` exists: closing
the review is the owner's step (§12 step 3). No fourth review round has read round 3's changes
(pitfall 74).

### Review log — round 2 (2026-09-24)

Two independent reviewers, both at $0: no provider or W&B call, no `--execute-live`, no `.env` read,
`checks.py` not read, nothing under heldout-2, promotion or audit read, and no repository file edited
by them. One reviewed the round-1 fixes for regressions (G); one checked launch readiness end to end
(L). **Verdict: RUN_WITH_CHANGES from both.** 9 findings: 1 blocker (L1), 8 minor. Every one is
applied below; none was rejected. The fixes changed the harness, so its sha256, the plan hash, the
dry plan (`dry-plan-r2/`), the numbers (`protocol_numbers-r2.out.json`) and the tests all moved
(§3). Both reviewers' "checked and sound" lists (the pins, spend bounds, the re-send pass through the
real provider, the R3 and F3 fixes, the fallback paths on the real plan, N's parity, the §9 figures,
the gate rehearsal, the live call path, the stop points and the ledger) are not repeated here. Their
evidence is in `review-r2/reviewer-evidence/`.

**Regressions lens**

| # | severity | finding | disposition |
|---|---|---|---|
| G1 | minor | Round 1's condition 5 counted prompts with at least one WORKING draw among three. At equal per-draw WORKING rates that count favours the arm whose draws vary more within a prompt, and T (0.7) against C (0) differs in exactly that way. Equal per-draw rates are equal yield in a loop that takes one slot-2 draw per study. With C clustered at ρ 0.8 (the protocol's own H-like C) and X at ρ 0.0, P(`RECOMMEND`) at the minimum of 6 was 0.0556 and 0.0557 at w 0.10, above 0.05; the mean prompt-count gain under that null was +1.1 to +2.8 prompts, a bias, not noise (`dispersion_null_by_k.out.jsonl`, 12,000 runs per cell). | **Applied, option (a).** Condition 5 is now the **working share gain**: over the 24 eligible prompts, the sum of X's WORKING share of its planned draws minus C's WORKING-or-missing share of its planned draws (§8.2). Each prompt adds between −1 and +1, and at equal per-draw rates the expectation is 0 however draws cluster. X's share is over its **planned** draws (a missing X draw is not WORKING), stricter than the reviewer's "of its received draws", to keep §8.2's worst case for X. The minimum was re-derived by the same simulation with the reviewer's scenarios added (C at ρ 0.8 with X at ρ 0.0 and at 0.2) and their reverse (X at ρ 0.8, C at 0.0): **8/3** (8 more WORKING draws of 72; worst cell 0.0387; 7/3 gives 0.0605). The round-1 minimum of 4 is unchanged (worst cell 0.0248), because with one draw per prompt the share is the prompt count. Under the yield null the share gain's mean is between −0.037 and +0.041 in every cell, while the old count's mean gain is +0.48 to +1.64 prompts where C clusters and X does not or mildly (+0.14 to +0.55 in the T-like cells), and its worst cell at 6 is 0.0587 on the new grid (`protocol_numbers-r2.out.json`). The old count is kept as a descriptive breadth figure. §8.2 and §14 say that an any-of-3 prompt count measures breadth, not per-draw yield. §9.2 and §9.3 (power, the family-wise figure) are recomputed. Tests: `test_the_working_share_is_not_moved_by_how_draws_cluster_within_a_prompt`, and `test_the_working_share_is_per_prompt_and_leaves_out_prompts_whose_slot1_policy_fires`, which now checks a missing C draw (5/3) and a missing X draw (4/3). Mutants N01–N03 and R2-G (re-pointed). |
| G2 | minor | Round 1's fallback made the round-1 rule the declared decision after any stop, so anyone watching the run could choose between the rules by stopping once round 1 was in (SIGTERM, or `kill -9` plus `--finalize-abandoned`). Every live line showed `class` and `policy_hash` in plain text. Stopping after `r0104` whenever round 1 alone recommends raised P(`RECOMMEND`) under the yield null 1.7 to 3.3 times, while each arm stayed under 0.05 (`optional_stop.out.jsonl`). | **Applied: option (a), with option (b) and the "also" items added.** (a) The fallback now applies only after a stop the operator does not choose: the run completed, or it stopped at the spend guard or at five errored requests in a row, or it crashed with its traceback recorded, **and** no stop signal was recorded (`fallback_permitted`). After SIGINT or SIGTERM, an operator stop of the re-send pass, or `abandoned` (declared an operator stop, since `kill -9` and a crash cannot be told apart there), an `INCOMPLETE` decision stays `INCOMPLETE`. (b) Live lines no longer carry `class`, `policy_hash`, `raw_sha256` or `matches_historical_raw`; the read-outs classify the raw text after the run. The manifest records the first stop signal (`stop_signal`: the signal, when it arrived, the request in flight, the last request, the requests and re-sends done) and `stop_signals_received`. `readouts.json` records `run_end` and whether the fallback was permitted, and why. `PHASE25_RESULTS.md` must quote the all-rounds partial contrast beside any round-1 decision (§8.6, §12 step 8). **What remains:** the rule still rests on the operator not causing an error stop, for example by cutting the network (§8.6 says so). Tests: `test_the_round1_fallback_applies_only_after_a_stop_the_operator_does_not_choose` (10 cases), the SIGTERM tests (where the signal arrived; no fallback), the live-loop tests (no classification on a line). Mutants N04–N09, N16, N17, M31. |
| G3 | minor | Four round-1 behaviours could be removed while all 62 tests passed, because an autouse fixture emptied the process list in every test: the real process list feeding the four checks (R2-F), the check right after the claim (R2-E), the consecutive-error stop in the re-send pass (R2-A), and the mechanism fallback's use of round-1 C (R2-C). "39 of 39 killed" and "a test covers each refusal" overstated coverage (pitfalls 48, 76). | **Applied.** The four tests the reviewer asked for: `test_the_real_process_list_feeds_every_paid_run_check_and_the_refusal_says_what_clears_it` (no `processes=`; `run_live` refuses before the claim), `test_a_paid_run_process_seen_only_after_the_claim_ends_the_run_at_zero_cost` (`ABORTED` / `another_paid_run_after_claim`, $0), `test_the_resend_pass_stops_at_the_fifth_errored_request_in_a_row` (6 eligible, all failing: `ended == 'consecutive_errors'` after 5), and the mechanism `round1_fallback` planned counts 26 and 26 (mechanism read-outs now report `planned_draws`). The mutation check was re-run on the round-2 harness with R2-A, R2-B, R2-C, R2-E, R2-F and R2-G included: 67 of 67 mutants killed, 88 tests passing unmutated (`review-r2/mutation/mutation-results.txt`; two earlier runs each left one survivor, below). §11's wording is corrected. |
| G4 | minor | The process guard matched substrings anywhere in any command line, so a process that merely mentioned `--execute-live`, `experiments/` and `.py` (a shell running grep, a test, a heredoc) blocked every check. It failed closed at $0, but with Phase 26 and 27 agents working in the repository a launch could be refused, or aborted right after its claim, again and again, each time using up a claim number and an `--out` directory (`process_guard_probe.out.txt`). | **Applied.** Tokens, not substrings (`paid_run_command`): the command line is split with `shlex` (whitespace if it cannot be parsed); the first token must be a Python executable; the script it runs (its first argument after Python's own options; `-c` and `-m` are not a script run) must be `scripts/experiments/<name>.py`; and a later token must be `--execute-live`, or an abbreviation argparse would accept for it (down to `--exe`). This last part is new: round 1's substring rule missed `--exec`. The fail-closed behaviour is kept. Test: `test_the_process_guard_matches_tokens_not_substrings_and_fails_closed` (the reviewer's decoy, grep, rg, a zsh heredoc, `-m`, `-c`, a caffeinate helper and an unparseable line are not runs; four real shapes are). Runbook: launch only when no other agent is working in the repository (§12). **Not done here:** Phase 26 uses the same substring rule. Its harness is outside this phase's files, so it was not edited; the rule (`paid_run_command` and the descendant exclusion) is passed to the Phase 26 review so that both can align. Mutants N11–N14. |

**Launch-readiness lens**

| # | severity | finding | disposition |
|---|---|---|---|
| L1 | **blocker** | The runbook's own launch command was refused at $0. `caffeinate -is <cmd>` keeps the original pid for `<cmd>` and forks a caffeinate helper as its **child**, whose command line repeats the launch arguments. The guard excluded only this process and its ancestors, so it reported its own helper as "another paid run", and `main()` rejected before the plan was built. The refusal suggested `--ignore-manifest`, which cannot clear a process. The docstring and the test modelled caffeinate as the parent (pitfall 76). Measured: Python pid 89830 with parent zsh; caffeinate pid 89831 with parent 89830 (`tree.log`, `guard_vs_caffeinate.log`). | **Applied, option (a), the harness fix.** The guard now excludes this process's descendants as well as its ancestors, and with G4's token rule a caffeinate helper is not a run by itself. Another run launched the same way is still caught, through its Python process. The docstring is corrected. The test's tree is replaced by the measured one (Python, then a caffeinate child carrying `--execute-live`: no blocker), with another run's Python-plus-caffeinate pair still flagged, a Python ancestor carrying the arguments excluded, and a descendant's descendant excluded (`test_the_process_guard_on_the_measured_caffeinate_tree_sees_no_run_but_this_one`). The refusal now says what clears each kind of blocker, and never offers `--ignore-manifest` for a process (`blocker_advice`). **Checked at $0 on the real process tree:** a stand-in named like the harness and started exactly as step 6 launches it (`nohup caffeinate -is ./.venv/bin/python …/scripts/experiments/slot2_probe.py --execute-live …`) loaded the real harness and asked its guard. Python kept the pid, caffeinate was its child, and the guard reported no blocker (`review-r2/process-tree/`). Step 2 was followed: `dry-plan-r2`, the numbers, the tests, a mutation check with descendant mutants (N10, and M28 for ancestors), and new pins. The same finding is passed to the Phase 26 review (`run_gap_probe.py` has the same guard, and `PHASE26_EXPERIMENT.md` the same launch). |
| L2 | minor | The machine was on battery (71%, discharging) during the review. The runbook requires mains power, and `caffeinate -s` prevents system sleep only on mains power (Phase 20 review item L9). | **Applied.** §12 adds a concrete pre-launch check to the checks table and to step 6: `pmset -g batt` must show `Now drawing from 'AC Power'`. The machine was still on battery (57%) when these fixes were made, so the operator must plug in before step 6. |
| L3 | minor | Step 2 was incomplete. The numbers script hardcodes `PLANNED_PLAN_HASH`, a `-r1` seed label and the `-r1` output name, so re-running it after a harness change reports `plan_hash_is_the_declared_one: false` unless it is edited. The mutation evidence was tied to the old harness. | **Applied.** Step 2 now lists every edit: `PLANNED_PLAN_HASH`, the seed label and the output file name in `slot2_protocol_numbers.py`, the re-run, and the mutation check against the new harness (copy `review-r2/mutation/` to scratch, run `prepare.py` and `mutate.py`, re-point any `SKIPPED` mutant). The numbers script's docstring says the same. Done for this round: `PLANNED_PLAN_HASH` is the `dry-plan-r2` hash, the seed is `faultlab-phase25-protocol-numbers-r2`, the output is `protocol_numbers-r2.out.json`, and the mutation check is in `review-r2/mutation/`. |
| L4 | minor | The working directory was not stated. Step 5 runs from `backend/`; steps 4, 6 and 8 need the repository root. `--readouts` resolves its directory against the current directory, while `--out` and `--finalize-abandoned` resolve against the repository root, so an operator left in `backend/` after step 5 got a safe failure. | **Applied (documentation, as proposed).** Steps 4, 6 and 8 start with `cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab` or say "from the repository root". Step 5 returns to the root. Step 8 says how `--readouts` resolves paths. The harness's path handling is unchanged. |
| L5 | minor | Step 3 asked for "the reviewers, the approver and the date" but named no keys. The gate checks only the three hashes, so the owner-approval part could come out in a different shape from earlier phases. | **Applied.** Step 3 names Phase 21's keys and value shapes: `phase` (25), `status` (`"approved"`), `approved_by`, `protocol_sha256`, `harness_sha256`, `plan_hash`, `reviewers`, `approved_at` (UTC). |

**Also found while applying round 2** (no reviewer raised these; recorded so they are not lost):
- **argparse abbreviations.** `argparse` accepts any unambiguous prefix of an option, so
  `--exec` launches a live run. The round-1 substring rule would not have seen it. The token rule
  counts prefixes down to `--exe` (`--ex` is ambiguous with `--expect-…`). Mutant N14.
- **Per-glob coverage.** No test named a Phase 21 or Phase 23 manifest or the Phase 21 claims
  directory; one shared loop was tested. A test now covers each glob and each claims directory
  (mutants N18–N20).
- **The first round-2 mutation run left N01 alive** (condition 5 decided by the breadth count):
  the dispersion test checked the share's value but not the decision. It now asserts that the
  decision fails on condition 5 alone (`mutation-results-run1.txt`).
- **The second run left N20 alive** (the Phase 21 claims directory dropped): the new claims-directory
  test took its list of directories from the harness under test, so the mutant shrank the test with
  it (pitfall 76). The list is now written out in the test (`mutation-results-run2.txt`).
- **No test pinned the declared minimums.** A harness with 7/3 or 3 would have passed every test; only
  the numbers script checked them. A test now pins 8/3 and 4 and checks each boundary (a gain of
  exactly 8/3 passes, 7/3 fails; 4 passes and 3 fails in round 1). Mutants N21 and N22.

**Closing for round 2.** All nine findings are applied. What moved: the harness (`f7190095…`), the plan
hash (`7b65ef3a…`), the dry plan (`dry-plan-r2/`), the numbers (`protocol_numbers-r2.out.json`; seed
`-r2`), the numbers script, and the tests (88, from 62). The status block still carries the
review-pending phrase, the "Reviewed for launch" line is absent, and no `review.json` exists: closing the
review is the owner's step (§12 step 3). No third review round has read round 2's changes (pitfall 74).

### Review log — round 1 (2026-09-24)

Three independent reviewers (statistics; run safety; rules and integrity), all at $0: no provider
call, no `.env` read, `checks.py` not read by any of them, nothing under heldout-2, promotion or
audit read, no repo file edited by them. **Verdict: RUN_WITH_CHANGES from all three.** 19 findings (7 major, 12 minor).
Every one is applied below; none was rejected. The fixes changed the harness, so the harness sha256,
the plan hash, the dry plan (`dry-plan-r1/`), the numbers (`protocol_numbers-r1.out.json`) and the
tests all moved (§3). Round 2 must review these changes (pitfall 74).

**Statistics lens**

| # | severity | finding | disposition |
|---|---|---|---|
| S1 | major | The working condition counted harmful policies: a draw was "working" if distinct and its step fired, and the harmful limit was a share of all distinct draws, so trivially distinct draws diluted it. An arm whose every working draw was a premature defer could be recommended (the reviewer's constructed case did exactly that). The simulations assumed harm only among non-firing draws; the store shows 3 of 9 firing policies harmful, 1 of 26 non-firing. | **Applied.** WORKING now excludes harmful draws (§7), and condition 5 counts WORKING only. The harmful condition is now a cap: at most half of X's distinct firing draws may be harmful (§8.2). I first implemented the reviewer's other option, a contrast of harmful draws per planned draw (X − C ≤ 0.10); under the store's harm model it refused 33–79% of arms firing at 0.25–0.40, so it penalised the arms that help most, and I replaced it before any data (evidence: `review-r1/dropped-harm-contrast/`). The simulations now use the store's rates (recomputed in `harm_model_from_store`); power and false alarms were re-run (§9). Tests: `test_firing_draws_that_are_harmful_do_not_count_as_working`, `test_the_harmful_limit_is_not_diluted_by_distinct_draws_that_do_not_fire`; the constructed case is re-run in `adversarial_cases` (now `NOT_RECOMMENDED`). |
| S2 | major | The quoted false-alarm rate ("at most 0.1%") held only for identical arms, where the absolute floors make a recommendation nearly impossible. Under the yield null (X more distinct, no more working) the 4-draw working floor recommended 7–26% of the time. | **Applied.** Condition 5 is now prompt-level: eligible prompts where X has a WORKING draw and C has none, minus the reverse, at least **6**. The numbers script chooses the minimum as the smallest for which P(`RECOMMEND`) under the yield null is at most 0.05 in the three clustering scenarios and the shared-effect model, at common firing rates 0.04 and 0.10 and D_X 0.80 and 0.90 (worst cell 0.0227 at 6; 0.0565 at 5). §9.2 now quotes the yield null; the identical-arm figure is labelled "identical-arm null only". Power is re-stated and is lower (§9.3). |
| S3 | major | The mechanism read-out's duplicate rate is over received draws, so H could "show copying" by returning `NO_CHANGE` or invalid output where C duplicates, with no distinct policy gained. | **Applied.** Two conditions added: distinct_H − distinct_C ≥ 0.30, and H's non-candidate share (`INVALID` + `STALE_PARENT` + `NO_CHANGE`) at most C's + 0.10 (§8.3). Test: `test_fewer_duplicates_from_outputs_that_are_no_policy_do_not_show_copying` (both cases give `NOT_SHOWN`). |
| S4 | major | §2 and §16 treated byte-identical rules text as evidence that slot 2 copies `raw_outputs`. Layout identity cannot tell copying from re-derivation: independent same-policy slot-1 pairs (no prior candidate) share the layout in 5 of 6. H's rationale rested on this. | **Applied.** §2.2 adds the independent-pair row (computed by the harness: `slot1_layout_identity`, 6 pairs, 5 rules-identical, census 4 of 5); §2's reading, §16 item 2 and H's rationale (§6) are restated as a hypothesis; the harness docstring too. |
| S5 | major | C1 re-sent slot 1's own request, so its "reproduces slot 1" rate was same-input determinism (the same event as its historical agreement, 25 of 26), and it lacked slot 1's source episodes. It could not separate copying from re-deriving slot 1's policy from the slot-2 evidence. | **Applied, as the reviewer's first option:** reference arm **N** (the verified slot-2 context with `candidate_history = []`, temperature 0, 1 draw) **replaces C1**, keeping 260 requests, the $12.96 bound and 40 attempts of headroom. N's rate of writing slot 1's policy is quoted beside the mechanism read-out; C1 is gone (§5, §6, §8.3, §13). The pre-check verifies N (2 new rows, 26 of 26), and N's prompt is parity-tested against the real Mechanic. |
| S6 | minor | The request order claimed "a short run keeps a complete first round", but no rule used round 1, and the one-run rule forbade a second run. | **Applied** with the safety lens's R1: a declared round-1 fallback (§8.6) with its own boundaries, its own working minimum (4, chosen the same way) and its own power (§9.3); the claim is replaced by plain consequences (§5). N moved into round 1's blocks, so round 1 is `r0001`–`r0104` with all four arms. |
| S7 | minor | "Working" did not record whether slot 1 already fired; 2 slot-1 policies fire, and the only historical distinct firing slot-2 draw is slot 1's policy lightly edited, so one prompt could supply 3 of the 4 draws condition 5 needed. | **Applied, the reviewer's preferred option:** each request's reference carries `slot1_step_fires` (and `slot1_harmful`); condition 5 counts only the 24 prompts whose slot-1 policy does not fire, and working draws on the other 2 are reported separately (§8.2, §8.4). The prompt-level count also stops one prompt supplying more than 1. Test: `test_the_working_count_is_per_prompt_and_leaves_out_prompts_whose_slot1_policy_fires`. |
| S8 | minor | Several studies share a slot-1 policy (22 of 26 distinct), so the sign test's p-values are somewhat optimistic. | **Applied.** Stated in §5 and §14; a descriptive sign test with prompts collapsed by slot-1 policy is reported beside each declared one (`sign_test_distinct_clustered_by_slot1_policy_descriptive`). |

**Run-safety lens**

| # | severity | finding | disposition |
|---|---|---|---|
| R1 | major | Any stop before about `r0249` (operator, a >12.5-minute outage, a crash) loses every declared decision, and the one-run rule forbids another run. An errored request is never sent again, so two short outage bursts can leave an arm below 75 of 78. | **Applied, options (a) and (c):** (a) a **re-send pass**: after a main pass that attempted every request, each request that errored with nothing delivered (transport, HTTP or provider errors; never a delivered generation, a local refusal or a mismatch) is re-sent once, blind and charged, under the same waits and stop rule (§10); (c) the **round-1 fallback** (§8.6). Option (b), a continuation run, was not adopted: its requests would be drawn after their block partners were seen. §5 now states the plain consequences. Tests: `test_live_loop_stops_at_the_spend_guard_and_retries_only_transport_failures`, `test_the_resend_pass_skips_anything_delivered_and_local_refusals`, `test_an_incomplete_decision_falls_back_to_a_complete_round_one`. |
| R2 | major | Most live-path guards were untested, so "A test covers each refusal" was false: 17 of 23 safety mutants survived the 37 tests. | **Applied.** The reviewer's E1–E7 are ported (SIGTERM during a request; SIGTERM in a wait; `--finalize-abandoned` charging recorded and in-flight attempts and counting delivery from the lines; the phase cap from an earlier undelivered run; a taken claim name; a review record naming another protocol, harness or plan; a stop at handler install), with tests killing M06, M11, M14–M21 (expected-earlier mismatch; a live `slot2_probe` pid; the line on disk before the manifest; generation-bearing errors; the pin and freeze checks called; no retry after a stop in the retry wait; the pre-plan paid-run check in `main`). The mutation check was re-run on the revised code with 16 more mutants on the new code. The first re-run left M12 (the live spend guard built on the requested cap, not the phase-cap remainder) and M29 (a delivered request re-sent) alive; two tests were added (`test_the_spend_guard_of_a_live_run_is_built_on_the_phase_cap_remainder`, and a generation-bearing `PROVIDER_ERROR` in the re-send test). The final run kills **39 of 39**, and two more gate tests cover the refusals no test had reached (the protocol not declaring the pins; the Mechanic role, with the pin check bypassed). Protocol line "A test covers each refusal" is now true (§11). |
| R3 | minor | A paid response was lost if classification raised before the line was written, and the run aborted with a delivered generation. | **Applied.** The descriptive classification runs in a guard that cannot raise (`describe_response`; class `None` and `describe_error` on failure), and the line is written and fsynced before the manifest counts it (§10). Tests: `test_a_classifier_failure_never_loses_a_paid_response`, `test_each_line_is_on_disk_before_the_manifest_that_counts_it`; the traceback test now injects a recorder failure instead. |
| R4 | minor | The plan hash depended on store-wide exclusion counts, so any new completion study of any configuration would move it and force a re-review. | **Applied** (with the rules lens's F5): the hashed plan counts only in-scope studies (`excluded_in_scope`); store-wide counts are in `dry-summary.json` only (§3). Test: `test_studies_outside_the_scope_never_enter_the_plan_counts`. |
| R5 | minor | Nothing re-checked other paid runs after the claim, and runners outside the globbed directories were invisible. | **Applied.** Right after the claim and the `STARTING` manifest, `other_paid_runs` runs once more; anything found ends the run `ABORTED` / `another_paid_run_after_claim` at $0 with nothing sent. The Phase 26 process-list guard (any `scripts/experiments/*.py --execute-live` process other than this one and its ancestors; fail closed) is added to every check (§11). Tests: `test_another_paid_run_seen_after_the_claim_ends_the_run_at_zero_cost`, `test_the_process_guard_ignores_this_process_and_its_parents_and_fails_closed`. |
| R6 | minor | The read-outs never showed which draws came from a blind retry, or how many timeouts each arm had. | **Applied.** Per arm: draws received on the blind retry, on the re-send, requests re-sent, `REQUEST_TIMEOUT` attempts, draws missing after every attempt, requests never attempted (§8.4). The optional recomputation without retried draws was not added: the counts show whether it would matter, and a second decision rule would need its own declaration. |

**Rules and integrity lens**

| # | severity | finding | disposition |
|---|---|---|---|
| F1 | minor | "`checks.py` is never opened" and "no held-out file is opened" were literally false: the configuration recompute imports `scorer_hash` and hashes the `backend/app` tree, including `checks.py`, `heldout_check.py` and `promotion.py` (the accepted Phase 20/21 pattern). | **Applied** (doc only): §3 and §15 reworded as the reviewer proposed. |
| F2 | minor | Byte-fidelity checks were narrower than §4 implied for the 5 Phase 17 prompts (`models.py` not covered by `source_hash` or `contract_hash`; no dependency-lock or model-settings comparison; parity on 4 of 52). | **Applied.** `verify_slot` compares `dependency_lock_hash` and `model_settings_by_role` and adds `stored_payload_canonical` (the stored bytes equal `canonical_json` of the context); the parity test covers all 52 stored contexts and all C, H and N prompts; §4 states what covers `models.py` for Phase 17. Tests: the tamper test fails exactly the new checks for a non-canonical payload, a changed model setting and a changed lock. |
| F3 | minor | The claim-following path took a sibling claim's `out` unvalidated, so a malformed or foreign claim naming `phase22-*` or `heldout2` would make the launcher read files there, and it did not skip `heldout-manifest.json`. | **Applied.** A claim's `out` is followed only if it is exactly `artifacts/phase2N-<x>/<name>` and not `phase22-*`, a claims directory, `.` or `..`; otherwise it is a blocker and nothing is read. `heldout-manifest.json` is skipped there too (§11). Test: `test_a_sibling_claim_is_followed_only_into_a_run_directory_and_never_into_the_seal` (a spy shows no path under `phase22` or `heldout2` is read). |
| F4 | minor | The determinism read-out compared H's draws with the historical output of the C request, a different input, which a results writer could quote as H determinism. | **Applied** (harness): historical agreement is computed for C only; H has repeat pairs only (§8.4). |
| F5 | minor | The same store-count dependency as R4. | **Applied** with R4. |

**Also noted, outside this phase:** the rules lens reported that `report_word_probe.py:132` (Phase 27)
globs `phase2[0-6]-*/**/*manifest*.json`, which recurses into `phase22-*`. That is Phase 27's harness;
it is passed to Phase 27's review and was not changed here.

### Closing entry (2026-09-25): round-3 fixes checked; approved for launch

- **Round-3 verification** (a focused check of round 3's fixes):
  - no code defect found;
  - 91 tests pass;
  - 89 of 91 mutants killed; the 2 survivors are the ones the fixer reported;
  - the dry run reproduces plan `5db5c880…` with 52 of 52 slots verified;
  - every pin equals its file.
- **The owner's decision:** "okay gi ahead with whater u recommend" (Shree Bohara, 2026-09-24),
  delegated to Claude as PM, who approves this phase. **No fourth review round is requested:**
  the round-3 verification read the round-3 diff and found no defect.
- **Launch conditions checked at launch time (§12 step 6):**
  - AC power;
  - no scheduled shutdown, restart or sleep;
  - **either automatic macOS update installation turned off or no update pending.** On
    2026-09-25, updates were pending (including a macOS update with a restart) and automatic
    installation was on. The owner was asked to turn automatic installation off before
    launch; the launch waits for that;
  - no other paid run is live.

