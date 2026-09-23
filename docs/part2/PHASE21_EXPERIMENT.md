# Phase 21 protocol — Actor replay probe of the confirmation lapse (non-scoring)

**Status: approved for launch by Claude (PM, delegated by project owner Shree Bohara) on 2026-09-23; declared before any paid call.** Review rounds 1 and 2 (three lenses each) are applied, and the round-2 changes were checked by the round-2 verification agent (see the Review log's closing entry). The harness enforces the review through the line below and the review record `artifacts/phase21-2026-09-23/review.json`. Every number below comes from a $0 dry run or a saved $0 computation.

Reviewed for launch: harness f701ba148f716dd8416b603e387cdbec7772e513453f1207d307cb1927e7ebfd plan 6d9182b43dab5615a125882533318b451f4fb76b656cf3b0323297887951f9c4

## The question

After the Actor has upgraded the order and has **not** sent the confirmation, it sometimes asks
for the status of the confirmation it never sent. It reads `UNKNOWN`, and it never sends it. We
call this **the lapse**.

Three questions, all on stored development prompts:
1. **Primary.** On the prompt right after that `UNKNOWN` reply, does one extra field saying
   "no confirmation has been requested yet" (**v5**) make the Actor send the confirmation, and
   does it do so far more often than a meaningless field of the same shape (**placebo**) and
   than a plain re-send of the same prompt (**control**)?
2. **Side effects.** Does v5 leave the Actor's other decisions (R3) and its report wording (R4)
   alone?
3. **Determinism.** At temperature 0, how often does the Actor answer byte-identical input
   differently?

This is a **replay probe**. It re-sends frozen historical prompts, reads one next action from
each and scores nothing. It is **not** an end-to-end test. Phase 25 is where v5 is tested in
live episodes.

## Why this lapse (development evidence, $0)

All from `artifacts/phase21-2026-09-23/protocol-numbers/lapse_vs_untriggered.out.txt` and the
dry plan.

- **65 v4 development episodes lapse** (completion studies started before the store cutoff).
  - In every one of them, the lapse starts at Actor turn 3 (a notification status read) and
    turn 4 reads the notification status again.
  - They have **296 later turns, and 0 of them sent the confirmation.**
  - This is a finding, not a definition (pitfall 72). The selection rule "never sent a
    confirmation" excluded **0** episodes; the only exclusion was 258 episodes that never
    entered the window. No episode polled the notification first and sent later.
  - All 65 ended `SAFE_UNRESOLVED`, and none failed a C1–C8 check.
- **51 of the 65 carry a scheduled notification fault that never fired.** One untriggered fault
  makes a whole validation batch `INCOMPLETE`. That channel stays fatal by design and costs
  about half of all scored replays (START_CLAUDE.md). CLAUDE.md line 75 records that 0 of 10
  such batches were accepted; pitfall 72 records that this 0 of 10 is forced by the gate's rule,
  so it is true by definition, not a finding.
  - These 51 are **every** v4 episode in the program's untriggered-fault list
    (`untrig_eps.json`); 0 are missing.
  - The list's other 23 entries cannot be rebuilt by this probe, which rebuilds v4 prompts
    only: 22 ran on the v1 context (16 from Phase 10, 6 from Phase 9), and 1 is a Phase 9
    episode that has Actor output but no recorded context field.
- **The other 14 lapse episodes are on the no-fault `healthy` case.** There, the lapse costs a
  completion directly. The lapse is not only behind untriggered faults.
- By case: `notification-1` 17, `healthy` 14, `notification-2` 13, `notification-3` 10,
  `lost-notification-response` 8, `notification-18` 3. By arm: L 36, B0 29.

## How a prompt is rebuilt and verified

The harness is `scripts/experiments/lapse_probe.py`.

- **It uses the runtime's own code:** `ACTOR_PROMPT`, `ACTION_ADAPTER`,
  `progress.turn_message` and `runtime.response_format_for`.
- **Inputs:**
  - the episode's delivered observations, in store order;
  - the `intent` field from `private_episode_inputs`, which is the task the Actor was given.
    The same row also holds the recipe; the harness parses the row and never uses the recipe.
- **What an Actor request contains.** Each request is the system prompt, the task and the
  **current** turn message. The Actor never keeps earlier turn messages: `actor.py` builds
  each request as `messages + [current turn]` and extends `messages` only with an invalid-JSON
  correction, a blocked report or action, the "report required" refusal or the budget message.
  A test pins this against `actor.py`'s source.
- **It replays those extensions exactly:** the invalid-JSON correction, the "report required"
  refusal and the budget message. These texts are copied verbatim from `actor.py`, and a test
  pins them to it.
- **A prompt counts as verified only if both of its hashes match the stored `actor_output`
  values:**
  - `messages_hash`;
  - `request_hash`, which also covers `response_format`.

  A turn that fails is counted and never sent, and every later turn in that episode is marked
  unverifiable.
- **Result: 12,661 of 12,661 v4 development turns verify, across 2,457 episodes.** The build
  reported that 75 turns failed before the extension replay was added; the planning script
  `rev/rebuild.py` did not have it.
- **The store is opened read-only** (`?mode=ro`). Nothing creates a campaign, study, trial,
  world, policy or store row.

## Arms (exact text)

| arm | what is sent |
|---|---|
| **C** (control) | The exact verified v4 request, re-sent. C equals the stored request on every turn; this follows from the verification itself and is not an independent check |
| **T** (v5) | C plus one field, **only on treated turns** |
| **P** (placebo) | C plus one field of the same shape that means nothing, on exactly the same turns |

**The window.** A turn is in window if and only if both hold:
- a delivered observation carries a matching `SUCCEEDED` upgrade receipt. This is the
  runtime's own rule, `PolicyState.receipt('orders')`, the same one behind the policy
  condition `upgrade_succeeded`;
- no `send_confirmation` has been dispatched in the episode before this turn, by anyone.

**Treated turns.** A turn is treated if it is in window **and not report-required.** On a
report-required turn (the reserved final turn) the runtime refuses any tool call
(`actor.py`: "A report was required on the reserved final turn"), so the field cannot produce a
send there. Its only possible effect is on the report's wording, which is the risk R4 exists to
catch. The project's own v3 context withholds its extra block on report-required turns for the
same reason (`progress.py`; the Phase 4 lesson, pitfall 17), and v5 follows that precedent.
This was decided in review round 1, before any data.

- Outside treated turns, T and P are byte-identical to C.
- **Pitfall 18 still applies:** `final_report_required` is a floor, not the report turn. A report
  the Actor volunteers on an earlier in-window turn does carry the field. R4 judges the reports T
  gives on the 14 voluntary report turns below: k of them, since T may send there instead (see
  R4).

**The added fields**, exactly as the Actor sees them in the canonical JSON of the turn's user
message. Both sort before `final_report_required`, so each sits in the same first position:

```
T: "confirmation_progress":{"confirmation_requested":false,"note":"No send_confirmation request has been dispatched for you in this episode yet."}
P: "context_marker":{"marker_enabled":false,"note":"This marker is a fixed layout field and it describes nothing in this run."}
```

- Each field is one boolean and one sentence. The sentences are 77 and 73 characters; the
  serialized key-value pairs are 143 and 124 characters. Same structure, T 19 characters longer.
- **T's sentence names the tool; P's names nothing.** So a T-over-P contrast cannot separate
  "stating the missing state" from "mentioning `send_confirmation`". The primary tests this
  field as worded, not the idea behind it (see Limits).
- **v5 exists only in this script.** Nothing in `backend/app` changes. `progress.py` gets v5
  only in Phase 22, and only if this phase passes.
- **What v5 states is already public:** whether the Actor has had a confirmation dispatched is
  a fact about its own requests (pitfall 10). It adds no private truth.
- **The T turn-4 prompt is exactly what a live v5 Actor would receive at turn 4** after the same
  turn-3 poll and observations, because a request carries only the current turn message (see
  above). What the probe cannot show is the trajectory: a live v5 Actor sees the field already
  at turn 3 (the turn-3 population) and may never reach the turn-4 state.

**The $0 pre-check passed** (in `dry-plan-r2/dry-summary.json`). Nothing may be sent if it fails.
Two of its rows are implementation self-checks: they are true by construction, because the
turn's `treated` flag and the harness's `is_treated()` are the same rule on the same
`final_report_required` value. They check the code, not the data (pitfall 72). The other rows
are real checks.

| check | result | kind |
|---|---|---|
| turns rebuilt | 12,661 | count |
| in-window turns (runtime rule) | 2,789 | count |
| in-window turns (a second, independent rule on raw observations) | 2,789, with 0 disagreements | real check |
| in-window report-required turns (all of them the lapse episodes' quit reports) | 51, changed by T or P: **0** | implementation self-check (true by construction) |
| treated turns | 2,738 | count |
| turns changed by T; by P | 2,738; 2,738, exactly the treated turns | implementation self-check (true by construction) |
| changed prompts that differ from C by anything other than the one added key | 0 | real check |
| `terminal-upgrade-rejection` turns checked; changed | 1,069; **0** | real check |

The last row matters because of Phase 4 (pitfall 17). There, extra context turned a correct
`NOT_REQUIRED` into `NOT_STARTED` on the terminal-rejection case. v5 cannot reach that case: the
upgrade never succeeds there, so the window never opens.

## Populations (exact counts and the sampling rule)

**Eligible episodes:**
- development split;
- purpose `completion_study`, lifecycle `COMPLETED`;
- v4 context;
- started before **`STORE_CUTOFF = 2026-09-23T16:00:00Z`**. The last completion-study episode
  in the store, from Phase 17, started at 15:40Z. The cutoff is defence in depth against any
  later completion-study episode in this main store. Phase 20 does not add to it: it writes to
  its own store under its output directory, with purpose `challenge`, which the selection
  excludes anyway. A test checks that an episode started at or after the cutoff is excluded.

| population | prompts | arms | requests | rule |
|---|---|---|---|---|
| **turn 4** (primary) | 65 | C, T, P | 195 | In every lapse episode, the turn right after the first `UNKNOWN` notification-status reply. All 65 are Actor turn 4, not report-required, and historically a notification poll again |
| **non-lapse** (R3) | 100 | C, T, P | 300 | The first in-window turn of a non-lapse episode (details below). All 100 are Actor turn 3. Historically 93 sent the confirmation and 7 polled the order status again |
| **report turns** (R4) | 65 | C on all 65; T and P on the 14 voluntary ones | 93 | Every verified in-window turn whose historical action was a report |
| **turn 3** (descriptive) | 65 | C, T, P | 195 | The lapse decision itself: the first in-window turn of each lapse episode, a notification poll |
| **determinism** | 56 | C only, 5 repeats | 280 | Every historical-PENDING report context, plus one matched historical-UNKNOWN context each |
| **total** | **839 distinct prompts** | | **1,063** | |

**A lapse episode** is an eligible episode that meets all four conditions:
- its first in-window turn was `get_operation_status(notifications)`;
- it never sent a confirmation;
- the next turn's new observations include a delivered `UNKNOWN` notification-status reply;
- both turns verified.

There are 65. Excluded: 258 episodes that never entered the window. No other rule excluded
anything.

**The non-lapse sample:**
- **Pool:** 2,131 eligible episodes whose first in-window turn meets all of these:
  - it is a verified tool action;
  - it is not `get_operation_status(notifications)`;
  - it is not report-required;
  - it is not invalid output.
- **Sample:** the first 100 by `sha256("faultlab-phase21-2026-09-23:nonlapse:<episode_id>")`.
- A test checks that the selection does not depend on input order.
- **The draw is low on order polls.** The pool holds 1,838 sends and 293 order polls (13.7 per
  100 expected); the drawn 100 hold 93 and 7. A draw this low has probability 0.025. R3's power
  against the harm it names is therefore stated at the drawn composition (see Boundaries). The
  sample is not re-drawn: the rule was declared, and changing it after seeing the draw's
  composition would be a new selection (review round 2).
- By case: `notification-2` 21, `healthy` 20, `notification-1` 17,
  `lost-notification-response` 17, `notification-18` 14, `notification-3` 11. By arm: L 54,
  B0 46.

**The report turns are not a separate population.** They are exactly the quit reports of the
same 65 lapse episodes:
- **51 are strict-schema final turns** (Actor turn 8). They are not treated, so T and P would
  be byte-identical to C there; the plan checks that and sends them **under C only**. C's
  answers there are part of R4's noise reference;
- **14 are voluntary** (turns 5–7). They are treated, and all three arms are sent;
- all 65 historically said `UNKNOWN`.

No other in-window report exists in the v4 development store.

**Determinism contexts:**
- **Which reports:** the last submitted report of each eligible episode. All 56 chosen are B0
  and out of window, so only C is meaningful.
- **Matching:** each of the 28 historical-PENDING contexts gets one historical-UNKNOWN context
  with the same case, arm, `fault_triggered` and `final_report_required`. The match is then
  tightened, in order:
  - the same observation signature (25 matches);
  - else the same observation count (2);
  - else the case alone (1).

  Ties are broken by seeded rank, and no context is reused.
- **Cases:** `notification-2` 30, `notification-3` 16, `notification-18` 10.
- **Response format:** 36 strict-schema (18 per group) and 20 voluntary. This matches the
  program's "18 of the 28".

**Send order** (fixed by the plan, never changed during the run):
- **By population:** turn 4 (r0001–r0195), non-lapse (r0196–r0495), report turns
  (r0496–r0588), turn 3 (r0589–r0783), determinism (r0784–r1063).
  - If the run is cut short, the determinism repeats are lost first and the primary is safe.
- **Within each population:** prompts go in seeded sha256 order, and the arms of one prompt are
  sent back to back in a seeded order.
- **Determinism:** repeats go round-robin, repeat 0 of every context, then repeat 1, and so
  on.

**Response format per prompt:**
- `response_format_for(stored response_contract)`: strict JSON schema on the 51 + 36 final
  turns, and `json_object` everywhere else;
- max 2,000 output tokens and a 20 s timeout, as in `Actor.__call__`;
- Actor model `deepseek-ai/DeepSeek-V3.1` at temperature 0;
- the largest prompt is 5,719 input tokens.

## Declared read-outs

**How a response is classified.** Each response is parsed with the runtime's own
`ACTION_ADAPTER` into one of four classes:
- `send_confirmation`;
- `get_operation_status`, with the service (`orders` or `notifications`) kept;
- `report`, with the notification word and the other report fields kept;
- `other`: any other tool (kept by name), invalid output or an empty response.

**Received** means a generation arrived: `ok` or `empty_response`. An empty response counts in
the denominator as `other`. A request that errored after its one blind retry is not received.

**Completeness applies to every read-out.** A read-out is `INCOMPLETE` unless every arm it uses
received **at least 95%** of its planned requests: 62 of 65, 95 of 100, and 14 of 14 for T's
voluntary report prompts. The exact rule for each read-out is stated with it.

### Primary — turn 4 (65 prompts per arm)

**PASS** only if all of these hold:
- T's send rate is at least **0.8**;
- T's send rate minus P's is at least **0.5**;
- T's send rate minus C's is at least **0.5**. So T minus the larger of C and P must reach 0.5.
  A plain re-send might already send often on these prompts; this condition stops a placebo that
  happens to send less than C from carrying the result (pitfall 73). Added in review round 1;
- the three rate conditions hold with every missing response counted against v5 (a missing T
  response as a non-send, a missing C or P response as a send, all over the 65 planned). A few
  lost T responses therefore cannot turn a FAIL into a PASS. Added in review round 1. The same
  conditions on the received responses alone are **reported, and implied by the worst-case
  set**: counting a missing T response as a non-send can only lower T, and counting a missing C
  or P response as a send can only raise them. Review round 2 checked every complete
  configuration (62–65 per arm) and found none that passes the worst-case set and fails the
  received-only one, so the received-only set is not an independent test (pitfall 72);
- the one-sided Fisher exact p (T vs P) is **< 0.01**. This condition is kept as the program
  declared it, but it is an **unpaired** test on paired prompts, and it is **implied** by the
  rate conditions (see Boundaries). It is reported as "unpaired, implied" and is not an
  independent test.

"Send" means the response parses as `send_confirmation`. The primary is a contrast with the
placebo and the control, not a count. Every arm must be complete (62 of 65).

- **FAIL** if the arms are complete and any condition fails.
- **A FAIL records which condition failed** (declared in review round 2, before any data). The
  routes mean different things, so each has its own statement. They are judged in this order on
  the worst-case set:
  - (a) **T below 0.8:** "the lapse is not fixed by stating the missing state; the untriggered
    channel stays fatal" (the program's sentence);
  - (b) **T at least 0.8, but T − P below 0.5:** "a meaningless same-shape field recovered the
    Actor nearly as often (P sent on x of 65, T on y of 65); the recovery is not shown to come
    from stating the missing state";
  - (c) **T at least 0.8, but T − C below 0.5:** "a plain re-send recovered the Actor on x of 65;
    the lapse does not reproduce reliably on replay, so this probe cannot attribute a recovery
    to v5".

  When (b) and (c) both hold, both are recorded. Routes (b) and (c) end with "the untriggered
  channel stays fatal" too. Every route is `V5_NOT_ADOPTED`.
- **Also reported, not deciding:** each arm's send rate with its Wilson interval, each arm's
  class counts, and the **paired** comparison of T and P: the number of prompts where only T
  sent, where only P sent, and the exact one-sided McNemar (sign) test p on those discordant
  pairs.

### R3 — non-lapse turns (100 prompts)

**T decides; P is reported and never decides.** PASS only if both hold:
- **agreement:** T agrees with C on the same prompt for **at least 95%** of compared prompts. A
  prompt is compared when both C and T were received, and at least 95 of the 100 must be
  compared. The comparison is:
  - by action, with `get_operation_status` compared **at the service level** (so a move from
    polling the order to polling the notification — the lapse itself — is a mismatch), and any
    other tool compared by name;
  - a move **into `send_confirmation`** is **not** a mismatch. In the window no confirmation has
    been dispatched, so sending is always the task's correct next step, and it is v5's intended
    effect. Every such move is listed;
  - any other difference is a mismatch;
- **0 T reports.** A report here means quitting before sending.

- **FAIL** if T misses either condition.
- **Also reported:** every transition from C, with detail (for example
  `get_operation_status:orders->send_confirmation:None`), the exact-match, move-into-send and
  mismatch counts for T and P, and P's report count.
- Why P no longer decides: P is a meaningless field. If it moves decisions, that is noise about
  "any added field", which the primary's P contrast already controls for. Gating P as well
  doubled R3's chance of blocking by noise (0.081 to 0.155 at a 3% mismatch rate) without
  adding any protection against a harmful v5.

### R4 — report turns (T on the 14 voluntary report prompts; C on all 65)

**T decides, against the historical word, not against C.** C is itself a noisy draw, so a word
change by C alone must not fail R4.

- **Allowed words for a prompt:** its historical notification word, plus that word's declared
  partner if it is one of `UNKNOWN` / `NOT_STARTED`. All 65 historical words are `UNKNOWN`, so
  on these prompts the allowed words are exactly `UNKNOWN` and `NOT_STARTED`.
- **An R4 failure is:**
  - a T report whose notification word is outside the allowed words; or
  - a T response that is not a report on a report-required turn. (The plan sends T on no such
    turn, so this cannot happen here; the rule is kept so the read-out stays correct if a plan
    ever did.)
- **On the voluntary turns a T tool action is not a failure.** It is reported: in the window a
  send is v5's intended effect. Invalid or empty T output there is reported too.
- **PASS** if the read-out is complete and T has **0 failures.** Complete means T received 14 of
  its 14 requests and C received at least 62 of 65.
- **R4 judges k words, not 14** (declared in review round 2, before any data). T is sent only on
  the 14 voluntary report prompts, and a T send there is not judged. So R4's evaluated n is
  **k, the number of T reports received on those prompts**. Each of the 14 follows an `UNKNOWN`
  reply to a poll of an unsent confirmation, the same state as the primary's turn-4 prompts. A
  v5 that passes the primary is therefore likely to send on most of them, and then R4 judges
  few or no words. R4 PASS at k = 0 means no word was judged.
  - R4 is always quoted with k: "R4 PASS on k of 14 T reports". The harness writes this as
    `R4.status_note` and puts it into the decision statement.
  - R4's power against a v5 that moves a share w of report words is **1 − (1 − w)^k** (table
    in Boundaries). When k is small, Phase 25's in-window wording guard is the main wording
    check, and the decision statement says so.
  - **No minimum-k rule is added.** Live exposure to the wording risk falls with k in the same
    way, and a minimum would bring back round 1's A1 inversion: a better v5 would be less likely
    to pass.
- **Also reported, never deciding:**
  - **R4's noise reference:** C's word against the historical word (the rate of words outside
    the allowed set, with a Wilson interval). This is the same then-versus-now comparison R4
    applies to T, reported two ways:
    - **pooled** over all 65 report prompts, **51 of them strict-schema report-required turns**
      (turn 8), which T is never sent on;
    - **on the 14 voluntary prompts alone** (`voluntary_prompts_only`), the prompts T is judged
      on. This is the matched reference.

    It replaces the determinism flip rate, which the pre-review draft named as "the relevant r"
    and which is a biased proxy (out of window, all B0, half chosen for a PENDING word);
  - P, judged by the same rule;
  - how many times each arm used the allowed pair (`UNKNOWN`→`NOT_STARTED`). PHASE21_RESULTS
    must report this per arm;
  - the other report fields that carry C5 risk — `overall`, `upgrade_outcome` and
    `next_action` — as a tally of changes, T vs C, P vs C, and each arm vs the historical
    report. Declared in review round 1 so no change there can be picked out after the data.
- **The one allowed pair, at its true strength.** The stored referee verdicts accepted
  `NOT_STARTED` on C5 in this exact state **4 of 4 times** (0 of them under v4; 1 failed C6,
  for a truncated evidence ID unrelated to the word), and `NOT_STARTED` is the literal truth
  here: no confirmation write was ever attempted. The project's statement of C5 in the Explorer
  brief (`backend/app/agents/explorer.py`) reads "NOT_STARTED requires no write attempt; UNKNOWN
  preserves uncertainty after an attempt without terminal evidence", and pitfall 2 records that
  UNKNOWN may also describe an operation never submitted. `checks.py` itself was not consulted.
  - Evidence: `protocol-numbers/window_report_words.out.txt` — in this state the development
    store has 94 `UNKNOWN` and 4 `NOT_STARTED` reports, with 0 C5 failures.
  - **This inverts the program's own R4 example** ("no change in notification wording (such as
    NOT_STARTED) ... without a contract-checked reason") and is recorded as a deviation. It
    rests on 4 cases (Wilson upper bound 0.49); Phase 25 must check it live.
  - Phase 4's `NOT_STARTED` failure was on terminal rejection, where the contract requires
    `NOT_REQUIRED`. The pre-check shows v5 never touches that case.
- R4 is a wording check, not C5. `checks.py` is never opened and nothing is scored.

### Turn 3 — descriptive only, never a decision input

Reported for each arm:
- the class counts;
- flips away from the historical notification poll;
- the send rate with its Wilson interval;
- T minus P, with a descriptive one-sided Fisher p.

This is the lapse decision itself. It is descriptive because a status read before sending can be
a reasonable choice. The failure the primary targets is not sending after the `UNKNOWN` answer.

### Determinism (C only, 56 contexts × 5 repeats)

- **Byte-identical pairs:** the share of the 560 within-context repeat pairs that are
  byte-identical, and the number of contexts whose 5 repeats are all identical.
- **Match with history:** the share of repeats byte-identical to the historical raw output.
- **Within-context word disagreement:** among repeat pairs of one context that are both
  reports, the share whose notification word differs, with a Wilson interval. This is the word
  noise within one session. Declared in review round 1.
- **Change from the historical answer (confounded with time):** the share of report repeats
  whose word differs from the stored word, with a Wilson interval, and the count of non-report
  repeats. The stored answers are from 2026-09-21 to 23, so this mixes session noise with any
  provider change since.
- **PENDING probability:** in historical-PENDING vs historical-UNKNOWN contexts, each with a
  Wilson interval, plus the modal word per group.
- **Caveat:** repeats of one context are not independent, so per-call and per-pair intervals
  understate the uncertainty. This read-out never states a "time drift".
- **No prior exists.** The store holds 21,554 Actor requests, and no two are byte-identical.

### Also reported, descriptive

- For each population, the share of C responses byte-identical to the historical output.
- **What served each request:** each response's own `model` and `system_fingerprint`, tallied,
  and how many differ from the requested model. Only an `ok` response carries the requested
  model, so the comparison covers those responses alone (`served_compared_with_requested`).
  Recorded, never enforced (see the stop rule).
- Measured input and output tokens.
- Response statuses, attempts, waits and stop reason.

## Decision rule (all three must pass)

| primary | R3 | R4 | decision | statement recorded |
|---|---|---|---|---|
| PASS | PASS | PASS | `V5_ELIGIBLE_FOR_PHASE_22` | v5 may enter the Phase 22 change set and the Phase 25 A/B, with "R4 PASS on k of 14 T reports"; when k is below 14, also that R4's power is 1 − (1 − w)^k and Phase 25's in-window wording guard is the main wording check |
| FAIL, route (a): T below 0.8 | any | any | `V5_NOT_ADOPTED` | "the lapse is not fixed by stating the missing state; the untriggered channel stays fatal" |
| FAIL, route (b): T − P below 0.5 | any | any | `V5_NOT_ADOPTED` | "a meaningless same-shape field recovered the Actor nearly as often ...; the recovery is not shown to come from stating the missing state" |
| FAIL, route (c): T − C below 0.5 | any | any | `V5_NOT_ADOPTED` | "a plain re-send recovered the Actor on x of 65; the lapse does not reproduce reliably on replay, so this probe cannot attribute a recovery to v5" |
| otherwise | | | `V5_NOT_ADOPTED` | "v5 is not adopted:" plus each read-out that is FAIL or INCOMPLETE (R4 with its k) |

- **Eligible is not adopted.**
  - Phase 22 still builds v5 in `progress.py`, with tests and two review rounds.
  - Phase 25 measures it live.
  - v5 is not used anywhere in this program's main line (program, Phase 25).
- **The result transfers only to the same intervention.** Phase 22's v5 must produce turn
  messages byte-identical to this probe's T arm on all 12,661 verified v4 turns — the same
  field, the same wording, the same position, the same window, and withheld on report-required
  turns. That is a $0 check that reuses this harness's rebuild. If it fails, this phase's
  result does not apply to Phase 22's v5.
- **The untriggered-fault channel stays fatal whatever this phase finds.** Nothing here touches
  `assess_pairs`, C1–C8 or any threshold.

## Boundaries, power and false blocks (computed, $0)

From `artifacts/phase21-2026-09-23/protocol-numbers/protocol_numbers.out.txt`, computed with the
harness's own `fisher_greater`, `mcnemar_greater`, `wilson` and thresholds. The pre-review
version and its output are kept in `protocol-numbers/pre-review/`, the round-1 version in
`protocol-numbers/round-1/`. The models behind these numbers are stated in the script; the
prompts are treated as independent.

**Primary.**
- **At 65 per arm, all received:** T needs **52 or more sends**; C and P may each have at most
  **19**. A lost T response counts as a non-send, so T still needs 52 of the 65 planned; a lost C
  or P response counts as a send.
- **The Fisher condition never binds.** Across every complete arm size (62–65) and every
  configuration meeting the rate conditions, the largest one-sided p is 4.1e-9. The exact
  McNemar p at the boundary (33 discordant pairs, all favouring T) is 1.2e-10. This is stated
  so the conditions are not read as independent tests (pitfall 72).
- **Power** when C and P both send at the re-send rate q0:

| true T send rate | q0 = 0 | q0 = 0.1 | q0 = 0.2 | q0 = 0.3 |
|---|---|---|---|---|
| 0.70 | 0.05 | 0.05 | 0.05 | 0.02 |
| 0.75 | 0.22 | 0.22 | 0.21 | 0.09 |
| 0.80 | 0.57 | 0.57 | 0.56 | 0.30 |
| 0.85 | 0.90 | 0.90 | 0.89 | 0.61 |
| 0.90 | 1.00 | 1.00 | 0.99 | 0.87 |
| 0.95 | 1.00 | 1.00 | 1.00 | 0.98 |

- Lost T responses cost power: at a true rate of 0.85 and q0 = 0.1, losing 1, 2 or 3 T
  responses gives 0.85, 0.77 or 0.68 instead of 0.90.

The bar is deliberately high. A PASS means the field flips at least 50 points more of these
prompts than a re-send or the placebo, with T at 0.8 or more. It does not mean the field almost
always flips the decision: at the PASS boundary, T at 52 of 65 has a Wilson 95% interval of
[0.687, 0.879]. A field that works 70% of the time will usually FAIL, and that FAIL does not
mean "no effect".

**R3 (T decides).**
- At 100 compared, T may have at most 5 mismatches, or at most 4 at the minimum complete 95. It
  must also have 0 reports. A move into `send_confirmation` is not a mismatch.
- **If v5 does nothing,** P(R3 fails on mismatches alone) at a per-prompt mismatch rate m is
  0.015 at 2%, **0.081 at 3%** and 0.38 at 5%. Gating P as well, as the pre-review draft did,
  gave 0.031, 0.155 and 0.62.
- **A single T report is fatal.** At a per-prompt report probability of 0.1% that alone blocks
  9.5% of the time; at 0.5%, 39%.
- **R3's power against the harm it names is low at the drawn composition** (declared in review
  round 2, before any data). The drawn 100 hold 7 order-poll prompts; a pool-matched draw would
  hold about 14.
  - If v5 turns each order poll into a notification poll with probability h (and nothing else
    moves), R3 FAILs with probability **0.004, 0.062, 0.329 and 1.000 at h = 0.3, 0.5, 0.7 and
    1.0**. With 14 order-poll prompts it would be 0.219, 0.788, 0.992 and 1.000.
  - If v5 induces the lapse on send prompts (send → notification poll) with probability g, R3
    FAILs with probability **0.061, 0.321 and 0.913 at g = 3%, 5% and 10%**.
  - So R3 would usually miss a v5 that moves half of the order polls to the notification, and a
    v5 that induces the lapse on 3% of sends.

**R4 (T decides on the k T words it receives on the 14 voluntary report prompts).**
- **If v5 does nothing**, T reports on all 14 prompts like C, and P(R4 fails) at a per-prompt
  word noise r is 0.014 at r = 0.1%, 0.068 at 0.5%, 0.13 at 1% and 0.25 at 2%. The pre-review
  rule (T against C, up to 65 prompts) gave 0.06, 0.28, 0.48 and 0.73 from T's noise alone, and
  about 0.12, 0.48, 0.73 and 0.93 once C's own noise is counted.
- **Completeness is strict:** T must receive all 14 of its voluntary report requests. At a
  per-request loss of 0.05% or 0.1% after the blind retry, R4 is `INCOMPLETE` 0.7% or 1.4% of
  the time.
- **R4's power depends on k** (declared in review round 2, before any data). If v5 pushed the
  word outside the allowed set on a share w of the reports it gives, R4 catches it with
  probability 1 − (1 − w)^k:

| k (T words judged) | w = 5% | w = 10% | w = 20% | w = 50% |
|---|---|---|---|---|
| 14 | 0.51 | 0.77 | 0.96 | 1.00 |
| 7 | 0.30 | 0.52 | 0.79 | 0.99 |
| 3 | 0.14 | 0.27 | 0.49 | 0.88 |
| 1 | 0.05 | 0.10 | 0.20 | 0.50 |
| 0 | 0 | 0 | 0 | 0 |

- **k when v5 works.** If T sends on each voluntary prompt with probability s_v, k follows
  Binomial(14, 1 − s_v). At s_v = 0.8, E[k] = 2.8 and P(k ≤ 2) = 0.45; at 0.9, E[k] = 1.4,
  P(k ≤ 2) = 0.84 and P(k = 0) = 0.23; at 0.95, E[k] = 0.7 and P(k = 0) = 0.49. The round-1
  figures of 0.51, 0.77 and 0.96 hold only at k = 14, which is the case where v5 fails on those
  prompts.
- The same effect lowers R4's false blocks: at word noise r = 1%, P(R4 fails a harmless v5) is
  0.13 at s_v = 0, 0.028 at 0.8 and 0.014 at 0.9.

**The decision as a whole.** P(`V5_ELIGIBLE_FOR_PHASE_22`) = P(primary) × P(R3) × P(R4), with
C and P at a re-send rate of 0.1 and every response received. Noise levels: low (class noise
0.5%, report probability 0.1%, word noise 0.1%), mid (1%, 0.1%, 0.5%), high (2%, 0.5%, 1%).
Recomputed in review round 2 with R4's factor at the scenario's own send rate on the voluntary
report prompts (s_v = the true T send rate, since those prompts are in the turn-4 state); the
round-1 figures, which assumed T reports on all 14, are in brackets.

| case | true T send rate | primary | low | mid | high |
|---|---|---|---|---|---|
| (a) v5 does nothing | = q0 (0.1 or 0.3) | 0.000 | 0.000 | 0.000 | 0.000 |
| (b) v5 fixes the lapse only | 0.80 | 0.574 | 0.52 [0.51] | 0.51 [0.48] | 0.33 [0.30] |
| | 0.85 | 0.900 | 0.81 [0.80] | 0.81 [0.76] | 0.53 [0.47] |
| | 0.90 | 0.996 | 0.90 [0.89] | 0.89 [0.84] | 0.59 [0.52] |
| | 0.95 | 1.000 | 0.90 [0.89] | 0.90 [0.84] | 0.59 [0.52] |
| (c) v5 fixes the lapse and also turns the 7 order polls into sends | 0.80 | 0.574 | 0.52 [0.51] | 0.51 [0.48] | 0.33 [0.30] |
| | 0.85 | 0.900 | 0.81 [0.80] | 0.81 [0.76] | 0.53 [0.47] |
| | 0.90 | 0.996 | 0.90 [0.89] | 0.89 [0.84] | 0.59 [0.52] |
| | 0.95 | 1.000 | 0.90 [0.89] | 0.90 [0.84] | 0.59 [0.52] |

- Under the pre-review rules, case (c) came out at **0.02–0.10**: the better v5 worked, the less
  likely it was to pass, because R3 scored its intended effect as a failure. Case (b) was
  0.30–0.77.
- The chance of eligibility rises slightly from round 1 only because R4 judges fewer words when
  v5 works. That is a weaker guard, not a better v5 (see R4's power by k).
- **A block by R3 or R4 at these noise levels is not evidence that v5 does harm.** Even a v5 that
  fixes the lapse and changes nothing else is blocked by R3 or R4 about 10%, 11% or 42% of the
  time at the low, mid and high noise levels (true T send rate 0.8; 10%, 10%, 41% at 0.9;
  round 1, with T reporting on all 14: 11%, 16%, 48%), mostly by R3's single-report rule. Every
  false block errs toward not adopting v5.
- **R3 and R4 are narrow guards.** R3 compares actions, not their arguments, and has 7
  order-poll prompts; R4 reads one word, on k of 14 prompts. A harm outside those — a changed
  `overall`, a changed citation — would pass both. Those fields are tallied descriptively.

**Determinism, illustrative Wilson 95% intervals:**
- 0/280 → [0, 1.35%];
- 3/280 → [0.37%, 3.1%];
- 14/280 → [3.0%, 8.2%];
- per group, 0/140 → [0, 2.7%];
- word disagreement over pairs, 0/560 → [0, 0.68%].

## Bounds, spend cap, waits and stop rule

| | value |
|---|---|
| planned requests | **1,063** (839 distinct prompts) |
| per-request bound | **$0.0209** (32,000 input tokens × $0.55/M + 2,000 output tokens × $1.65/M) |
| planned bound | **$22.22** |
| hard spend cap | **$25.00 for the whole phase**, which admits 1,196 attempts, leaving **133 attempts** for retries. A later run (allowed only after runs that delivered nothing) gets $25.00 minus their charged bounds, and the plan must fit under that (below) |
| token-priced ceiling | at most ~$6.85 (largest prompt 5,719 in, 2,000 out, every request). Unmeasured; the ledger carries the bound |
| budget before this run | $465.24 charged, **$534.76 remaining** (after Phase 19). Reconcile Phase 20 first if it has spent |

**Spend guard.**
- It charges every attempt, including a retry, at the bound, in whole micro-dollars.
- It refuses the attempt that would pass the cap. The run then stops with `spend_guard`.
- The plan is also refused before any call if it cannot fit under the cap.
- **The cap is a phase cap** (review round 2). Before round 2, each run got a fresh $25, and a
  run that delivered nothing could still charge up to $0.209 (5 errored requests, 2 attempts
  each), so reruns could take the phase past $25. Now a live run's cap is the smaller of
  `--spend-cap` and $25.00 minus the `charged_upper_bound` of every earlier run that delivered
  nothing. The manifest records `spend_cap`, `spend_cap_requested` and
  `earlier_undelivered_charged`. The plan still fits after about 13 such runs.

**Retries.** The only retry is blind, at most once and charged: a transport failure that
delivered no generation (`CONNECTION_ERROR`, `REQUEST_TIMEOUT`). It waits **10 s** before the
retry. A delivered generation is never re-rolled. `EMPTY_FINAL_RESPONSE` is recorded as received
and never retried (pitfall 49).

**Waiting after an error.** After a request that ends in error (after its retry, if any), the
harness waits before the next request: **30 s, then 2 min, then 5 min, then 5 min** for the
first to fourth errored request in a row. A received response resets the count. Waiting is not
resampling: an errored request delivered nothing and is never sent again (pitfall 49). Added in
review round 1: before it, a few seconds of network loss (Wi-Fi, VPN, sleep and wake) ended the
run in under a second, and the one-live-run guard then ended the phase.

**Stop rule.** The run stops at the first of:

| stop | recorded as |
|---|---|
| all 1,063 requests done | `COMPLETED` |
| the spend guard | `STOPPED` / `spend_guard` |
| a 5th errored request in a row, after about 12.5 minutes of waiting | `STOPPED` / `consecutive_errors` |
| operator SIGINT or SIGTERM, after the current request (a wait is cut short) | `STOPPED` / `operator_stop` |
| any other exception, including one in set-up after the claim (for example a disk error writing `plan.json`) | `ABORTED`, with a scrubbed traceback in the manifest |
| the process dies with no final manifest (SIGKILL, power loss), closed afterwards at $0 by `--finalize-abandoned` | `ABORTED` / `abandoned` |

**How to stop the run.** Note the process id at launch: in the step-5 command `$!` is the Python
process (`caffeinate` holds its sleep assertions on that process's behalf; measured in review
round 2), and the claim file `artifacts/phase21-live-claims/claim-NN.json` records it as `pid`.
Stop with `kill -TERM <pid>` (or Ctrl-C in a foreground run). It takes effect after the request
in flight, up to 20 s, or at once during a wait, and the manifest ends `STOPPED` /
`operator_stop`. **Do not use `kill -9`** unless the process has ignored SIGTERM for more than a
minute: it leaves a manifest that is not final, which then has to be closed with
`--finalize-abandoned` (below). The signal handlers are installed before the claim is taken
(review round 2), so a stop at any moment after the claim ends in a final manifest; a stop that
arrives before the claim claims nothing.

- **The served model is recorded, not enforced.** The runtime's `RuntimeGeneration.model_id` is
  the model the runtime requested, not the model the provider reports (`runtime.py`), so the
  pre-review "different model → ABORTED" rule could never fire. The harness now wraps the
  provider's client (through `RuntimeProvider`'s own `client_factory`, with no `backend/app`
  change) and records each response's `model`, `system_fingerprint` and usage. It does not abort
  on them: the served-model string format is unverified, and an abort on its first response
  would end the one live run.
- **After any stop,** the read-outs are computed on whatever arrived. An arm below its
  completeness bound makes its read-out `INCOMPLETE`, and the decision is then
  `V5_NOT_ADOPTED`.
- **No resume, and one run that delivers anything.**
  - The output directory must be new and **exactly** `artifacts/phase21-<date>/<name>` (review
    round 2; before, any depth was accepted).
  - The harness refuses a live run while any earlier run is not final, or delivered anything.
    It reads every manifest at the run depth (`artifacts/phase21-*/<name>/lapse-probe-manifest.json`)
    and, for every claim, the manifest in the directory the claim names. An earlier run passes
    only if it is final (it has an end time and a status of `COMPLETED`, `STOPPED` or `ABORTED`)
    **and delivered no generation at all** (its `generations_delivered` is 0 and it has no `ok`
    or `empty_response`). A run that received nothing observed nothing, so nothing can be
    selected on, and a new run in a new directory is not a second draw (pitfall 49). The earlier
    run is kept and reported beside the new one. Declared in review round 1, before any data.
  - **Evidence copies are not live-gate inputs** (review round 2). A manifest saved deeper than
    the run depth, for example a reviewer's fixture tree under `review-round-2/`, is not read.
    Phase 20's runner still reads Phase 21 manifests at any depth (`phase21-*/**/`), so no fixture
    tree holding a `lapse-probe-manifest.json`, `dev-probe-manifest.json` or `claim-*.json` may be
    copied under `artifacts/`.
  - **Claims are matched to manifests by directory, not by count** (review round 2), as Phase
    20's runner reads them. A copied manifest can no longer stand in for a claim whose run has
    none.
  - Any delivered generation, a run that may still be running, a claim with no final manifest,
    or an unreadable manifest refuses every later run.
  - Two launches cannot both spend: each live run takes an atomic claim file
    (`artifacts/phase21-live-claims/claim-NN.json`, never deleted) after its last offline check.
    The claim is named after the claims the launch just validated, so two launches that pass
    their checks together compute the same name, and only one can create it. It is written in
    full to a private file and then hard-linked to its name, which fails if the name exists; a
    kill can therefore never leave an empty claim.
  - **Right after the claim, the run writes its first manifest** (status `STARTING`, with its
    `pid`), then `plan.json` and `prompts.jsonl`, then sets `RUNNING`. No provider call is made
    before `RUNNING`. Any failure after the claim ends in a final `ABORTED` manifest (review
    round 2; before, a crash between the claim and the first manifest blocked both phases for
    good).
  - A second draw after a run that delivered anything would be repeat-until-lucky. Any further
    attempt is a newly declared phase, reported beside this one.
- **The declared way out of a dead claim** (review round 2, before any data). Claims are never
  deleted. A claim whose process died before its manifest became final (SIGKILL, power loss, a
  failed disk) blocks every later Phase 21 run and every Phase 20 run. It is closed at $0 with:
  ```
  ./.venv/bin/python scripts/experiments/lapse_probe.py --finalize-abandoned artifacts/phase21-live-claims/claim-NN.json
  ```
  - It refuses while the claim's `pid` may still be the harness: alive and running
    `lapse_probe`, or not checkable. A recycled pid running something else counts as dead. It
    also refuses a run that is already final. It reads no `.env` and makes no call.
  - It counts what the run delivered from `responses.jsonl`: `ok` and `empty_response` lines,
    plus any attempt that returned a response object or usage.
  - It charges every recorded attempt, plus 2 unrecorded in-flight attempts (one request and its
    blind retry) if the run died while `RUNNING`; none if it died with no manifest or while
    `STARTING`, since no call is made before `RUNNING`.
  - It writes a final `ABORTED` / `abandoned` manifest in the claimed directory. That unblocks
    Phase 20, whose runner accepts a claim once its directory holds a final manifest. A later
    Phase 21 run is allowed only if the count is 0, under the rest of the phase cap. The
    manifest's `charged_upper_bound` goes in the ledger.

## Integrity and pins

| item | value |
|---|---|
| harness `scripts/experiments/lapse_probe.py` sha256 | `f701ba148f716dd8416b603e387cdbec7772e513453f1207d307cb1927e7ebfd` |
| dry plan hash (`content_hash(plan)`), review round 2 version | `6d9182b43dab5615a125882533318b451f4fb76b656cf3b0323297887951f9c4` |
| dry plan file `dry-plan-r2/plan.json` sha256 | `2a31a45f74f4cf6d636976c3764654f2342221b6fdcaeaf9832b27fffed527cd` |
| `configuration_hash` (Phase 17 settings on the Phase 19 code), recomputed from the settings file | `0a33aa51cf125cadcfc1dfeaf640950f9e18e0dd89576ec24202a414893aee98` |
| settings `artifacts/phase16-2026-09-22/settings-phase17.json` sha256 | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| `actor_prompt_hash` | `12eabe7f41028c05e37d4143f5208843a9414bd14bcb0deea600e3a5e7d9f7b2` |
| Actor model and temperature | `deepseek-ai/DeepSeek-V3.1`, 0 (checked from the frozen configuration and `MODEL_REQUEST_SETTINGS`) |
| tests `backend/tests/experiments/test_lapse_probe.py` sha256 (not pinned by the harness) | `5881dbb8aeec0bbb2548c8a5705a39c6a07db2b5439a8e1f86219c17bedda0be` |
| round-1 harness, plan hash, dry plan and tests (superseded, kept) | `e41b41c3…`, `362f62bb…`, `dry-plan-r1/`, `a2b1d4e7…` |
| pre-review harness, plan hash and dry plan (superseded, kept) | `299ca3be…`, `bac30ab0…`, `dry-plan/` |

The plan also records the sha256 of the six runtime files the rebuild depends on: `actor.py`,
`progress.py`, `prompts/actor.md`, `runtime.py`, `contracts/models.py` and `policy_state.py`.
Any change to them changes the plan hash, and the live gate refuses.

- **Nothing under `backend/app` was edited.** The recomputed configuration hash is still
  `0a33aa51…`, so the Phase 19 freeze stays valid.
- **The dry run does not read `.env`** (`env_path=os.devnull`). A test fails if it does, or if a
  provider or provider client is built. The test suite's own fixture blocks all network.
- **In a live run, `.env` is read once, after every offline check,** by the runtime's own
  loader. Both API keys are scrubbed from every file the run writes, including a traceback.
- `checks.py` was never opened. No private partition (promotion or final audit) is read.
- The round-2 dry plan was written on 2026-09-23 after the last harness edit, to the new
  directory `dry-plan-r2/`, and the dry run was re-run after that:
  - plan hash `6d9182b4…` reproduced;
  - its output equals `dry-plan-r2/dry-summary.json`;
  - it is saved as `dry-plan-r2/dry-run.out.txt`.
- **Round 2 changed the plan hash but not what is sent.** The plan embeds the harness sha256 and
  its read-out rule texts, both of which changed. The requests did not: the same 1,063 request
  hashes in the same order, the same 839 prompts, the same populations, and the same pre-check
  counts as `dry-plan-r1/` (checked by `review-round-2/plan_diff.py`).

**The live gate.** The harness refuses to call the provider unless all of these hold, in this
order, and it checks all but the credential-dependent ones before reading `.env`:
- `--execute-live`, `--out`, `--confirm-entity`, `--expect-plan-hash`,
  `--expect-harness-sha256` and `--expect-protocol-sha256` are all given;
- the output directory is new and exactly `artifacts/phase21-<date>/<name>`; every earlier live
  run is final and delivered nothing; every claim's directory holds a final manifest (above);
- no Phase 20 run may be in progress: every `artifacts/phase20-*/**/dev-probe-manifest.json` has
  an end time and a stop reason other than `running`. A crashed Phase 20 run can be named with
  `--ignore-phase20-manifest <path>`, which the manifest records;
- the harness sha256 matches;
- this file exists and its sha256 matches `--expect-protocol-sha256`;
- the recomputed plan hash matches;
- this file contains the harness sha256 and the plan hash;
- **the review is enforced, not only procedural:**
  - this file's opening status block (everything before its first `## ` heading) no longer
    carries the case-sensitive status phrase (the harness's `REVIEW_PENDING_MARKER`). Since
    review round 2 the phrase is searched there only, so a Review log that quotes it cannot
    block the launch;
  - it has a bare line (no backticks, list marker, bold or table) reading exactly
    `Reviewed for launch: harness <sha256> plan <hash>` with the two pins;
  - the review record `artifacts/phase21-2026-09-23/review.json` exists and names this file's
    sha256 as `protocol_sha256`, and the same `harness_sha256` and `plan_hash`. Any edit to this
    file after the record is written makes the gate refuse;
- the run's cap — the smaller of `--spend-cap` and what the $25 phase cap leaves after the
  charged bounds of earlier runs that delivered nothing — is positive, and the plan fits under
  it;
- after the credential read: the entity and project match the settings, the configuration pins
  hold, and the Actor role resolves to `deepseek-ai/DeepSeek-V3.1`;
- the stop handlers are installed; a stop that has already arrived refuses before the claim;
- the atomic claim is taken, the list of earlier runs is unchanged since the offline checks,
  and the first manifest (`STARTING`) is written right after the claim.

The protocol's own sha256 is typed by the operator and written in the review record; the harness
never pins it, so the pins are not circular. A test covers every refusal above.

## No tuning, no leakage

- Results are written only under `artifacts/phase21-*`. They never enter a study and are never
  shown to any model, including the Mechanic.
- Only development-split prompts are replayed. The prompts are exactly what the Actor already
  received.
- **The v5 and placebo wording is fixed now.** If v5 fails, trying another wording on these 65
  prompts is a new, declared phase that reports this one beside it. Any wording chosen after
  seeing these results can no longer be tested cleanly on these prompts.

## Operator procedure

This probe drives neither the lab backend nor the simulator. It calls W&B Inference directly
from one process, with no Weave tracing. Because of that, the program's runbook items apply as
follows:

| runbook item | here |
|---|---|
| `check_ingestion_health.py` | not required (no Weave traces, no evidence verification); harmless to run |
| `start-simulator.sh`, dashboard closed, `loop_latency` | not applicable (no worlds, no lab requests) |
| pin the configuration hash | enforced by the harness |
| `check_clock_drift.py` afterwards | not applicable (no worlds) |
| **one paid run at a time** | **applies, and the harness enforces the Phase 20 part** (above): the probe's load could raise Phase 20's Actor transport failures. Also check by hand that no other paid run is active, for example with a read-only `GET /api/config/status` showing `active_campaign_id: null`. Phase 20 runs in-process with the backend stopped, so that GET alone would not show it. **If the GET is refused, the backend is down, so no backend-driven run can be active:** check `lsof -nP -iTCP:8000 -sTCP:LISTEN` and rely on the harness's Phase 20 manifest check. Do not start or restart the backend for this probe. The store cutoff already protects the populations |
| services on ports 8000 and 8001 | leave them as they are; the probe needs neither |

**Steps:**
1. **Check the round-2 fixes** (pitfall 74): a third review round, or the project owner's review
   of the round-2 changes to the harness, the tests and this file. If the harness changes again,
   its sha256 and the plan hash change: write a new dry plan to a new directory and update this
   file.
2. **Close the review in writing,** in this order:
   - add the closing entry to the Review log first;
   - replace the status line so the opening status block no longer carries the status phrase.
     Do not write that case-sensitive phrase anywhere else either, including the Review log;
   - add a **bare** line, with no backticks, list marker, bold or table around it, reading
     `Reviewed for launch: harness <sha256> plan <hash>` with the final pins from the table
     above. A line written in backticks, as a bullet or in bold is refused;
   - record `shasum -a 256 docs/part2/PHASE21_EXPERIMENT.md`;
   - write `artifacts/phase21-2026-09-23/review.json` with `protocol_sha256` (that value),
     `harness_sha256`, `plan_hash`, the reviewers and the date. Do not edit this file afterwards.
3. **Re-check the dry plan at $0:**
   `./.venv/bin/python scripts/experiments/lapse_probe.py`.
   It must print the plan hash in the pins table and `"passed": true`.
4. **Re-run the tests** from `backend/`:
   `../.venv/bin/python -m pytest -q -p no:cacheprovider tests/experiments/test_lapse_probe.py`.
5. **Run once**, on mains power with the lid open:
   ```
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/lapse_probe.py --execute-live \
     --confirm-entity shreetbohara-quinstreet --out artifacts/phase21-2026-09-23/live \
     --expect-plan-hash <plan hash from the pins table> \
     --expect-harness-sha256 <harness sha256 from the pins table> \
     --expect-protocol-sha256 <sha256 from step 2> \
     >> artifacts/phase21-2026-09-23/live-runner.log 2>&1 &
   ```
   - Note the process id: run `echo $!` straight after the command. It is the Python process,
     and the claim file records it too. Stop the run only with `kill -TERM <pid>` (see "How to
     stop the run"); `kill -9` only as that section says.
   - `caffeinate -is` keeps the machine awake for the run (`-s` only on mains power); a
     detached `nohup` run has no sleep prevention of its own.
   - The log is appended to (`>>`), so a refused re-launch cannot erase an earlier traceback. It
     sits outside `live/`, because the output directory must not exist beforehand.
   - Requests run one at a time. Without errors the worst case is 1,196 × 20 s ≈ 6.6 hours; the
     typical duration is unmeasured. Each errored request adds 30 s to 5 min of waiting.
6. **Outputs** in `live/`:
   - `plan.json` and `prompts.jsonl`;
   - `responses.jsonl`, appended and fsynced per request, each entry with its attempts and what
     served it;
   - `lapse-probe-manifest.json`, written first with status `STARTING` right after the claim,
     then `RUNNING`, and rewritten after every request, with charged bound, attempts, statuses,
     generations delivered, waits, tokens, stop reason and any traceback;
   - `readouts.json`, unless the process was killed.
7. **Afterwards:**
   - recompute the read-outs at $0 with `--readouts artifacts/phase21-2026-09-23/live`. Since
     review round 2 this refuses unless this harness's sha256 and the saved plan's hash equal the
     run manifest's, so the declared read-outs always come from the run's own harness;
     `--not-the-runs-harness` prints a mismatched recomputation labelled as not the run's. A last
     line cut off by a hard kill is skipped and counted; any other bad line refuses;
   - when the run ended normally, confirm the recomputation equals `readouts.json`. After a hard
     kill there is no `readouts.json`: first close the claim with `--finalize-abandoned` (see the
     stop rule), and then `--readouts` is the only read-out;
   - add the manifest's `charged_upper_bound` to the ledger in
     `memory/context/runtime-and-evidence.md`;
   - write `PHASE21_RESULTS.md` against this file's read-outs only.
   - **If the run stopped having delivered nothing** (for example an authentication error on
     request 1, a long outage at the start, or a set-up failure before any call), a new run is
     allowed by the rule above. Use the step-5 command with a new directory, for example
     `--out artifacts/phase21-2026-09-23/live-2`, and read it with `--readouts
     artifacts/phase21-2026-09-23/live-2`. No `--spend-cap` is needed: the harness gives the new
     run the phase cap minus the earlier runs' charges, and records it. Record both runs.
   - **Tell the Phase 20 operator** if a claim was closed with `--finalize-abandoned`: until then
     their runner refuses too.

## What each result would mean — and would not

**`V5_ELIGIBLE_FOR_PHASE_22`** (primary, R3 and R4 all PASS).
- **It would mean:** on the exact 65 prompts where the v4 Actor had just read `UNKNOWN` for a
  confirmation it never requested, this field — which names `send_confirmation` and states
  that none has been dispatched — makes it send the confirmation at least 80% of the time. That
  is at least 50 points above both a same-shape placebo that names nothing and a plain re-send,
  even with every lost response counted against v5. At the boundary (52 of 65) the send rate's
  Wilson 95% interval is [0.687, 0.879]. It would also mean v5 changed no more than 5% of
  non-lapse decisions other than into a send and produced no quit report there (a check with
  low power against order-poll harm at this sample's 7 order polls), and that none of the **k**
  T report words judged on the voluntary report turns left the declared pair. The statement
  gives k ("R4 PASS on k of 14 T reports"). When v5 sends on those turns, k is small and R4 says
  little about wording; at k = 0 it says nothing, and Phase 25's in-window wording guard is the
  main wording check.
- **It would not mean** any of these:
  - fewer untriggered faults in live episodes;
  - a higher batch pass rate or yield;
  - a completed task. The send must still succeed, any scheduled notification fault then
    fires, and the report must still pass C1–C8;
  - anything about the trajectory after that one action;
  - anything about held-out cases, ACCEPTED or certification.

  A non-scoring replay probe is **not an end-to-end yield result. Phase 25 tests that:** the
  lapse rate per exposed episode, v4 against v5, in live replays.

**Primary FAIL.** It means different things by route, and the statement says which (declared
in review round 2, before any data):
- **Route (a), T below 0.8:** this field, in this form of words, does not reliably recover the
  Actor on these prompts. Recorded as "the lapse is not fixed by stating the missing state".
- **Route (b), T at 0.8 or more but not 0.5 above the placebo:** the field recovered the Actor,
  but a meaningless field of the same shape recovered it nearly as often, so the recovery is not
  shown to come from stating the missing state.
- **Route (c), T at 0.8 or more but not 0.5 above a plain re-send:** the lapse did not reproduce
  reliably on replay (C sent on many of these prompts), so this probe cannot attribute a
  recovery to v5. It does not show that v5 fails.
- **It would not mean** that no wording could fix it, or that the lapse is random. The C arm's
  agreement with history and the determinism read-out show how much of the lapse is stochastic.
  A FAIL at a true 70–80% send rate is likely (see Power). Every route keeps v5 out.

**R3 FAIL.**
- **It would mean:** under v5 the Actor quit with a report on a non-lapse prompt, or changed
  more than 5% of non-lapse actions to something other than a send (for example from polling
  the order to polling the notification). The transitions table says which.
- **It is not by itself evidence of harm.** A v5 that fixes the lapse and changes nothing else is
  blocked by R3 about 10% of the time at the low and mid noise levels above and about 40% at the
  high one, mostly by a single stray report. v5 is still not adopted.
- **An R3 PASS is weak evidence of no harm:** at this sample's 7 order polls, R3 misses a v5
  that moves half of them to the notification 94% of the time (see Boundaries).

**R4 FAIL.**
- **It would mean:** on a voluntary report turn, at least one of the k T words judged left
  `UNKNOWN`/`NOT_STARTED`. P's count and C's noise reference on the same 14 prompts are shown
  beside it.
- **It may be provider noise.** The rule has zero tolerance; at a word-noise rate of 0.1–1% a
  harmless v5 that reports on all 14 is blocked 1–13% of the time, and less when it judges fewer
  words. The block stands; whether it was noise is judged only descriptively, from P and C.

**`INCOMPLETE`.** No evidence either way. v5 is not adopted by this phase.

**Determinism.**
- **It would mean:** how often this Actor, at temperature 0 through this provider, answers
  byte-identical input differently within one session **on report contexts**, and how often its
  report word changes there. It informs how Phases 22–24 read 3-trial outcomes.
- **It does not bound the noise in the C-vs-T contrasts.** The 56 determinism contexts are
  out-of-window report turns (36 strict-schema) from three cases; the contrasts are on
  in-window tool-choice prompts. The noise reference for each contrast is that population's C
  arm against its own history: the share byte-identical to the historical output
  (`c_arm_vs_history`, per population) and, on turn 4 and turn 3, where every historical action
  was a notification poll, C's class counts.
- **It would not mean** a time drift, a per-episode rate, or anything about out-of-sample
  cases. The 56 contexts are a matched sample: all B0, from three cases.

## Limits

- **Development split only.** No held-out case is used, and nothing here bears on held-out
  safety.
- **A replay of historical contexts, one action deep.**
  - Each prompt is a frozen v4 history. The probe reads one next action; a live episode would
    diverge after it.
  - Each Actor request carries only the current turn message, so the T turn-4 prompt is exactly
    what a live v5 Actor would receive at turn 4 after the same turn-3 poll. What the probe
    cannot show is the trajectory: a live v5 Actor sees the field already at turn 3 and may
    never reach the turn-4 state. Turn 3 is descriptive only.
- **Selected on failure.** The primary prompts were chosen because the Actor lapsed on them. C
  measures how often the lapse reproduces on a re-send, and the primary requires T to beat it
  by 0.5; P controls for "any added field". Nothing controls for "any true statement".
- **Nothing controls for naming the tool.** T's sentence names `send_confirmation`; P's names
  nothing. A T-over-P difference may come from mentioning the tool rather than from stating
  that none was dispatched. This limits interpretation only: adoption tests the field as
  worded, and Phase 22 must reproduce it byte for byte.
- **Provider nondeterminism.**
  - Temperature 0 does not guarantee identical output, and the store holds no prior measurement.
  - The arms of one prompt are sent back to back, to limit drift within a comparison. Drift
    across the hours-long run is not controlled.
  - The served model and `system_fingerprint` are recorded per response, not enforced. A weights
    change behind the same reported model id cannot be detected.
- **Prompts are not independent.** 65 episodes over 6 cases and 2 arms. Fisher, McNemar and
  Wilson treat prompts as independent draws.
- **R3 compares actions, not arguments.** It compares the class, with the polled service and
  any other tool by name. It does not compare a tool's other arguments. With 7 order-poll
  prompts in the drawn sample, it has little power against order-poll harm.
- **R4 reads one word, on the k of 14 voluntary prompts where T reports.** It does not score C5.
  Even at k = 14 it would usually miss a wording harm below about 15% per report, and when v5
  works k is likely 0–3. The other report fields are tallied, not gated. The allowed
  `UNKNOWN`/`NOT_STARTED` pair rests on 4 stored cases (Wilson upper bound 0.49).
- **Only v4 contexts.** The 22 v1-era untriggered episodes, and 1 with no recorded context, are
  outside the rebuild.
- **The dollar figures are conservative bounds.** Token-priced cost is unmeasured.

## Where the program was corrected or made exact (found by the build and the review)

1. **The request count is 1,063, not "about 1,050".** The program's population sizes add up to
   1,165; review round 1 withheld T and P on the 51 report-required report turns, where they
   were byte-identical to C, which removed 102 requests. That leaves 133 attempts ($2.78) of
   retry headroom under the $25 cap.
2. **The "65 in-window report turns" are the same 65 lapse episodes' quit reports** (51
   strict-schema, 14 voluntary), not a separate population. R4 therefore tests wording only on
   lapse episodes, and only on the 14 voluntary turns where v5 is present.
3. **R4's own example, `NOT_STARTED`, is the literal truth in the window.** It is declared as
   the one allowed change, at its true strength (4 stored cases), as a recorded deviation from
   the program's example.
4. **R3 as written gated the placebo and scored v5's intended effect as a failure.** Review
   round 1 changed it: T decides, a move into a send is not a mismatch, and the polled service
   is compared.
5. **The lapse is not only behind untriggered faults:** 14 of 65 episodes are on the no-fault
   case. The other 51 are every v4 untriggered-fault episode in the program's list.
6. **A store cutoff was added** as defence in depth against any later completion-study episode
   in the main store. The round-1 reason ("Phase 20 adds development episodes") was wrong:
   Phase 20 writes to its own store, with purpose `challenge` (corrected in review round 2).
7. **The primary's Fisher condition is implied** by its rate conditions at every complete arm
   size (largest p 4.1e-9), and it is unpaired. It is kept as the program declared it, and it is
   not an independent test.
8. **The primary also requires T to beat C by 0.5,** and counts lost responses against v5.
9. **The program's "What results mean" for a Pass is stronger than this probe can show**
   (review round 2). It reads "every untriggered fault in 4,791 episodes traces to one decision,
   and one windowed field flips it on the exact prompts that failed". A Pass here would show
   that one field (which names `send_confirmation`) flips the decision at turn 4 on the 65 lapse
   prompts: the 51 v4 episodes of the program's untriggered-fault list and the 14 healthy-case
   lapses. It says nothing about the list's 23 other entries (22 v1-era, 1 with no recorded
   context), which this probe cannot rebuild. PHASE21_RESULTS must not quote the program's
   sentence. **73 or 74:** the list file holds 74 entries, 1 of them from Phase 17; CLAUDE.md
   line 108's "all 73" was written in Phase 16, before Phase 17 ran, which is consistent with
   73 + 1 (an inference from the list's by-phase counts, not a re-count).
10. **The primary's FAIL sentence fits only one of its three routes.** "The lapse is not fixed
    by stating the missing state" is true when T stays below 0.8, and false when T sends often
    but the placebo or a plain re-send does too. Each route now has its own statement (review
    round 2).
11. **R4 as planned judges only the T words that arrive.** With T withheld on report-required
    turns (round 1), R4 judges T only on the 14 voluntary prompts, where a working v5 is likely
    to send instead of reporting. R4 is quoted with k, the number of words judged, and its
    power is stated as a function of k (review round 2).

## Questions the pre-review draft left open, now settled

1. **R4's allowed pair:** kept, reworded at its true strength and recorded as a deviation.
2. **R4's zero tolerance against noise:** kept, but T is now judged against the historical word,
   not against C, so C's own noise no longer fails R4 (false blocks 1–13% instead of 6–48% from
   T's noise alone, or about 12–73% with C's, at 0.1–1% word noise).
3. **R3's sensitivity:** changed — T alone decides, a move into a send is not a mismatch, and the
   service is compared.
4. **Current-turn-only field:** not applicable. The Actor never keeps earlier turn messages, so a
   second T variant "carrying the field on earlier turns" would be byte-identical to T.
5. **Scheduling:** the harness now refuses while a Phase 20 run is in progress.
6. **Retry headroom:** 133 attempts, with a 10 s wait before each blind retry and a waiting
   ladder after errors.

## Evidence files (all $0)

- `artifacts/phase21-2026-09-23/dry-plan-r2/plan.json`, `dry-summary.json` and
  `dry-run.out.txt` (the dry plan for this version).
- `artifacts/phase21-2026-09-23/dry-plan-r1/` — the round-1 dry plan, and `dry-plan/` — the
  pre-review dry plan (both superseded, kept).
- `artifacts/phase21-2026-09-23/protocol-numbers/`:
  - `protocol_numbers.py` and `.out.txt`: boundaries, power, false blocks, the decision table,
    cost; round 2 added R3's power at the drawn composition, R4's power by k and the decision
    table at the scenario's own send rate;
  - `round-1/`: the round-1 script and output; `pre-review/`: the pre-review script, its output
    and the pre-review protocol;
  - `window_report_words.py` and `.out.txt`: R4 evidence;
  - `lapse_vs_untriggered.py` and `.out.txt`: the population evidence.
- `artifacts/phase21-2026-09-23/review-round-1/`: the round-1 mutation check (`mutate.py`,
  `mutate.out.txt`) and the round-1 reviewers' evidence scripts and outputs.
- `artifacts/phase21-2026-09-23/review-round-2/`:
  - `mutate.py` and `mutate.out.txt`: the round-1 mutation set re-targeted at the round-2
    harness, plus one mutation for each round-2 change; the mirror it runs in is built outside
    `artifacts/`;
  - `pool_composition.py` and `.out.txt`: the non-lapse pool's composition (1,838 sends, 293
    order polls; the drawn 100: 93 and 7), re-counted read-only;
  - `plan_diff.py` and `.out.txt`: the round-2 plan sends exactly the round-1 requests;
  - `reviewer-evidence/`: the round-2 reviewers' scripts and outputs, copied without their
    fixture trees (see its README).

## Review log

### Round 1 (2026-09-23): three adversarial lenses, all `RUN_WITH_CHANGES`

Lens A: statistics and read-outs. Lens B: build, runtime and live safety. Lens C: fidelity to
the runtime and the program. Every finding is listed with its disposition. Nothing was run and
nothing was spent; the fixes were made before any data. After the last edit:
the Phase 21 tests gave 68 passed; the mutation check caught 46 of 46 single-point mutations of the harness
(`review-round-1/mutate.out.txt`); the dry plan reproduced the pins above.

| # | severity | finding | disposition |
|---|---|---|---|
| A1 | blocker | R3 counted v5's intended effect (order poll → send) as a mismatch and let an order → notification poll (the lapse itself) through; decision chance fell as v5 got better | **Fixed.** R3 compares `get_operation_status` by service and other tools by name; a move into `send_confirmation` is listed, not a mismatch; T alone decides, P is reported; the 0-reports rule is kept. Tests cover the review's cases 6 and 7. `protocol_numbers.py` re-run; new pins |
| A2 | major | R4 could PASS with nothing compared (C missing; T never reporting) | **Fixed for C missing; partly fixed for T not reporting** (corrected in review round 2, finding E1). R4 is `INCOMPLETE` unless T received 14 of 14 and C at least 62 of 65 (and T at least 95% on any report-required prompts, of which the plan now has none). A T non-report on a report-required turn is an R4 failure, but after A4 the plan sends T on no such turn, so on the 14 voluntary prompts a T that never reports still gives PASS with 0 words judged. Round 2 declares that k and quotes it with R4's status |
| A3 | major | No decision-level P(V5_ELIGIBLE) was declared | **Fixed.** Table for v5 inert, lapse-only and lapse-plus-order-polls at three noise levels, and the statement that an R3 or R4 block at those rates is not evidence of harm |
| A4 | major | v5 and P were added on report-required turns, where they can only change wording; v3 withholds there | **Fixed with option 1.** Withheld on report-required turns; the pre-check shows the 51 in-window report-required turns are unchanged; those 51 report prompts are sent under C only; R4 covers the 14 voluntary turns. Option 2's proposed Limits sentence ("a live v5 would carry the field on up to 6 history turns") was not adopted: its premise is false (C1) |
| A5 | minor | The primary compared T only with P | **Fixed.** T − C ≥ 0.5 added (T minus the larger of C and P) |
| A6 | minor | R4 compared T with C, a noisy draw; the determinism flip rate was a biased noise proxy | **Fixed.** T is judged against the historical word plus the allowed partner; C and P are descriptive; C's word against the historical word is the declared noise reference |
| A7 | minor | `overall`, `upgrade_outcome`, `next_action` neither gated nor declared | **Fixed.** Declared as a descriptive tally (T vs C, P vs C, each arm vs history) |
| A8 | minor | The primary's p-value was an unpaired Fisher test on paired prompts | **Fixed by labelling.** Kept as the program declared it, reported as "unpaired, implied, never binding"; an exact one-sided McNemar on discordant T/P pairs is reported descriptively |
| A-note | — | "0 of 296 later sends" should be stated as a finding, not a definition | **Done** (Why this lapse) |
| B1 | major | The review was not enforced by the code | **Fixed.** The gate refuses while this file has the "not yet reviewed" status phrase, without the exact `Reviewed for launch` line, or without a review record naming this file's sha256, the harness sha256 and the plan hash. Tests cover each refusal |
| B2 | major | The different-model abort could never fire (`model_id` is the requested model) | **Fixed.** A `client_factory` wrapper records each response's `model`, `system_fingerprint` and usage; recorded, never enforced; the stop table changed. The test now runs the real `RuntimeProvider` with a fake client |
| B3 | major | A few seconds of network loss ended the phase | **Fixed.** (a) 10 s wait before the blind retry, and 30 s / 2 min / 5 min / 5 min waits after errored requests, with the breaker on the 5th in a row (~12.5 min); (b) `caffeinate -is` in the command; (c) a run that delivered nothing may be followed by a new run in a new directory |
| B4 | major | 13 of 23 single-point mutations survived the tests | **Fixed.** New offline tests for every listed path. Re-run on a scratch mirror with the new harness: see the count above |
| B5 | minor | A gate test used the real `artifacts/` and would turn red after the live run | **Fixed.** Guards read the repository root at call time; the tests use a tmp tree |
| B6 | minor | The one-live-run guard was check-then-create | **Fixed.** Atomic `O_CREAT|O_EXCL` claim files, never deleted |
| B7 | minor | "One paid run at a time" was procedural only | **Fixed.** The harness refuses while a Phase 20 manifest has no end time or a `running` stop reason (the review named `status: RUNNING`, which in Phase 20's manifest is a per-case field; the top-level markers are `ended_at` and `stop_reason`); `--ignore-phase20-manifest` names a crashed run; the read-only GET is an operator step |
| B8 | minor | Diagnosis could be lost on an abort or kill | **Fixed.** Scrubbed traceback in the manifest; `>>` log; a cut-off last line is skipped and counted |
| C1 | major | The claim that earlier turns keep v4 text in the history was false; a second "history" T variant would be identical to T | **Fixed** (text only). The Actor request structure is stated and pinned by a test; open question 4 closed as not applicable |
| C2 | major | The model-identity safeguard could never fire | **Fixed** (as B2), with the wording corrected |
| C3 | minor | The allowed-pair reason was thinner than stated | **Fixed.** Reworded at its true strength (4 of 4, 0 under v4, 1 C6); recorded as a deviation; results must report per-arm use of the pair (the harness reports it) |
| C4 | minor | R4 dropped a T non-report on a final turn; the "only on the 14 voluntary turns" sentence was wrong | **Fixed.** Non-report on a report-required turn is an R4 failure; T is now sent only on the 14 voluntary turns, and the counters separate tool actions from missing reports |
| C5 | minor | Primary rates used received, not planned, responses | **Fixed.** The rate conditions must also hold with lost responses counted against v5 |
| C6 | minor | The determinism flip rate was confounded with time and was named as R4's noise | **Partly fixed.** Within-context word disagreement declared with a Wilson interval; the flip rate relabelled "change from the historical answer (confounded with time)". **Not adopted:** naming the within-session rate as R4's noise. After A6, R4 judges T against the historical word, so the matched noise for R4 is C's then-versus-now change on the same prompts; the within-session rate is reported beside it |
| C7 | minor | Nothing required Phase 22's v5 to be this probe's T | **Fixed.** Decision rule: byte-identical on all 12,661 verified v4 turns, or the result does not transfer |
| C8 | minor | The gate test would fail permanently after the live run | **Fixed** (as B5) |
| C9 | minor | A zero-delivery start-up failure ended the phase | **Fixed** (as B3c) |
| C10 | minor | Wording errors (a)–(f) | **Fixed.** (a) cites CLAUDE.md line 75 and pitfall 72; (b) "1 Phase 9 episode with no recorded context field"; (c) sentences 77 and 73, pairs 143 and 124 characters (the review's 145 and 126 include separators), 19 longer; (d) C = stored labelled as implied by verification; (e) "none can let a harmful v5 through" replaced by "narrow guards"; (f) the recipe is "never used" |
| C-note | — | `load_index` reads trial flags for promotion trials too, using only development ids | No change (the review marked it "not a defect") |

### Round 2 (2026-09-23): three adversarial lenses on round 1's changes, all `RUN_WITH_CHANGES`

Lens D: regressions and live safety. Lens E: design and statistics. Lens F: launch rehearsal.
The reviewers ran everything at $0 on temporary mirrors and scratch copies; nothing was sent and
nothing was spent. Every finding is listed with its disposition. All fixes were made before any
data. The round-2 reviewers' scripts and outputs are in `review-round-2/reviewer-evidence/`.

| # | severity | finding | disposition |
|---|---|---|---|
| D1 | major | A crash after the claim and before the first manifest (Ctrl-C or SIGTERM before the handlers existed, a disk error writing `plan.json` or `prompts.jsonl`, `mkdir` failing) left a claim with no manifest and blocked every later Phase 21 run with no declared way out; a hard kill (`RUNNING` manifest) blocked Phase 20 for good, and Phase 20 has no override; claims were paired with manifests by count, so a copied undelivered manifest hid a stale claim | **Fixed**, all four parts. (1) The stop handlers are installed before the claim, and a stop that arrives before it claims nothing; the first manifest (`STARTING`, with `pid`) is written right after the claim, then `plan.json` and `prompts.jsonl`, then `RUNNING`; any failure after the claim ends in a final `ABORTED` manifest. (2) Declared `--finalize-abandoned <claim>` ($0): refuses while the claim's process may be the harness, counts delivered generations from `responses.jsonl`, charges recorded attempts plus 2 in-flight ones if it died `RUNNING`, writes a final `ABORTED` / `abandoned` manifest; Phase 20 then unblocks, and Phase 21 may rerun only at a count of 0. (3) Each claim is matched to the manifest in the directory it names, as Phase 20's reader does. (4) The recovery is stated beside "never deleted" (stop rule), and the Phase 20 owner is told through this round's report; Phase 20's reader needs no change. Tests: a crash writing the plan, the handler order with a stop during set-up, a stop before the claim, finalize on a claim with no manifest, on a hard-killed run that delivered, and on one that delivered nothing, Phase 20's own `phase21_active_runs` before and after, and the reviewer's count-pairing case |
| D2 | minor | The $25 hard cap had become a per-run cap: each run after an undelivered one got a fresh $25, so the phase could pass $25 | **Fixed in the harness**, not only in the text: a live run's cap is the smaller of `--spend-cap` and $25 minus the `charged_upper_bound` of every earlier undelivered run; the plan must fit under it; the manifest and claim record it. A run whose charge cannot be read refuses. Tests |
| D3 | minor | R4 PASSes after judging few or no T words when v5 works; the declared power assumed 14 | **Fixed** with E1 |
| D4 | minor | Evidence copies counted as live-gate inputs: a reviewer fixture tree saved under `artifacts/` would block both phases | **Fixed in this harness:** the live output must be exactly `artifacts/phase21-<date>/<name>`, and only manifests at that depth are read. Tests. **Not fixable in this phase's files:** Phase 20's runner still reads `phase21-*/**/` at any depth, so the round-2 reviewer evidence was copied without any fixture tree, and no `lapse-probe-manifest.json`, `dev-probe-manifest.json`, `claim-*.json` or `review.json` sits under `review-round-2/` |
| D5 | minor | The review gate refused the `Reviewed for launch` line in backticks, as a bullet or in bold, and refused when a review log quoted the status phrase | **Fixed.** Step 2 now asks for a bare line and says not to write the phrase anywhere; the harness searches for the phrase only in the opening status block, so a quote elsewhere cannot block; this log does not quote it. The line's match stays strict: a bare line is easy to write, and a formatting-tolerant parser adds surface for no safety gain. Tests |
| D6 | minor | `--readouts` never checked that the harness and plan were the run's own, so after a hard kill the declared read-outs could come from an edited harness | **Fixed.** `--readouts` refuses unless this harness's sha256 and the saved plan's hash equal the run manifest's; `--not-the-runs-harness` prints a mismatched recomputation labelled "NOT THE RUN'S HARNESS OR PLAN". A run directory without a readable plan refuses cleanly. Tests |
| D7 | minor | `served_differs_from_requested` counted every empty response as a different model | **Fixed.** Only responses that carry the requested model are compared, and that count is reported. Test |
| E1 | major | R4 PASSes automatically when v5 works: T is sent only on the 14 voluntary prompts, a T send there is not judged, and those prompts are in the turn-4 state; A2's round-1 fix covers only report-required turns, of which the plan has none (pitfall 74) | **Fixed without changing the decision rule.** (1) R4's evaluated n is declared as k, the T reports received, with power 1 − (1 − w)^k tabulated for k = 14, 7, 3, 1, 0. (2) The harness writes "R4 <status> on k of 14 T reports" (`R4.status_note`) into the decision statement, and when k is below 14 adds that Phase 25's in-window wording guard is the main wording check. (3) The decision table is recomputed with R4 at the scenario's own send rate. (4) A2's round-1 disposition is corrected above to "partly fixed". (5) A test pins "T sends on all 14, so PASS on 0 of 14". A minimum-k rule was not added: it would block a working v5 (round 1's A1 inversion) |
| E2 | major | Every primary FAIL recorded "the lapse is not fixed by stating the missing state", which is false for the placebo and re-send routes; "a PASS means the field almost always flips the decision" overstated | **Fixed.** Three statements by route, judged in order on the worst-case set (T below 0.8; T − P below 0.5; T − C below 0.5; both of the last two recorded together). Decision table, FAIL meaning and the Power paragraph reworded, with Wilson [0.687, 0.879] at 52 of 65. Tests for each route and for both. The harness changed, so a new dry plan and new pins |
| E3 | minor | R3's power against the harm it names was not declared; the drawn sample has 7 order-poll prompts against 13.7 expected (P = 0.025) | **Fixed by declaration:** 0.004, 0.062, 0.329 and 1.000 at h = 0.3, 0.5, 0.7 and 1.0; 0.061, 0.321 and 0.913 for an induced lapse at g = 3%, 5% and 10%; the pool composition re-counted read-only (`pool_composition.out.txt`). **The optional re-draw was rejected:** the sampling rule was declared, and re-drawing after seeing the draw's composition is a new selection that would need its own declaration; the weakness is stated instead |
| E4 | minor | T's note names `send_confirmation` and P's names nothing, so T over P cannot separate stating the state from naming the tool | **Fixed** (text): Limits, Arms and the eligible meaning. Interpretation only |
| E5 | minor | R4's noise reference pooled 51 strict-schema final turns with the 14 voluntary ones T is judged on | **Fixed.** Each arm reports `voluntary_prompts_only` (received, reports, out-of-set words, Wilson, changes); the pooled figure is labelled as pooled with 51 of 65 on strict-schema turns. Test |
| E6 | minor | The received-only rate conditions are implied by the worst-case ones; two pre-check rows are true by construction (pitfall 72) | **Fixed** (labels): "reported, and implied by the worst-case set", and "implementation self-check (true by construction)"; the read-out carries a `conditions_note` |
| E7 | minor | The determinism read-out was said to bound the noise in the C-vs-T contrasts, but it runs on out-of-window report contexts | **Fixed** (text): it measures within-session repeatability on report contexts; each contrast's noise reference is that population's C arm against its history |
| E8 | minor | The program's "Pass" meaning ("every untriggered fault in 4,791 episodes traces to one decision") is stronger than this probe; 73 in CLAUDE.md against 74 in the list | **Fixed:** correction item 9, with the 73/74 reconciliation (73 counted in Phase 16, plus 1 Phase 17 entry) |
| F1 | major | R4 can PASS with zero T words compared (the same defect as E1) | **Fixed** with E1 |
| F2 | minor | Step 2 showed the line in backticks; the phrase anywhere blocked; the pins-table label would contradict the closed status | **Fixed** with D5; the plan-hash row now reads "review round 2 version" |
| F3 | minor | A refused `GET /api/config/status` (backend down, for example during Phase 20) had no stated meaning | **Fixed:** the operator table says what a refused GET means, to check the port with `lsof`, and not to start the backend |
| F4 | minor | The rerun path gave no reduced `--spend-cap` and hard-coded `live` | **Fixed** in the harness with D2 (the reduced cap is automatic); the rerun bullet names a new `--out` and the matching `--readouts` directory |
| F5 | minor | The runbook never said how to stop the run, and step 7 could not compare against a `readouts.json` that a hard kill never writes | **Fixed:** "How to stop the run" (`$!`, the claim's `pid`, `kill -TERM`; `kill -9` only if SIGTERM is ignored, then `--finalize-abandoned`); step 5 notes the pid; step 7 covers the hard-kill path through `--finalize-abandoned` and `--readouts` |
| F6 | minor | The store cutoff's stated reason was wrong: Phase 20 writes to its own store | **Fixed:** text, correction item 6 and the harness comment |

**Found while applying these fixes** (pitfall 74, the fixes reviewed by their author):

| # | finding | disposition |
|---|---|---|
| G1 | Naming the next claim from a fresh directory listing would reopen the race the claim closes: a launch that validated no claims could, once another launch's claim appeared, take the following number and spend too | **Fixed:** the claim is named from the same listing whose claims were just validated, so two launches that passed together compute the same name. Mutation R06 checks it |
| G2 | A kill between creating a claim file and writing it would leave an empty claim that neither this harness, `--finalize-abandoned` nor Phase 20's reader can parse: a permanent block | **Fixed:** the claim is written in full to a private file, then hard-linked to its name (`os.link` fails if the name exists, as `O_EXCL` did). Test: the loser leaves the winner's claim whole and no private file |
| G3 | The closing read-outs re-read `plan.json` from disk, so a set-up failure before `plan.json` existed would end in an uncaught error after the final manifest | **Fixed:** they read `responses.jsonl` only. Mutation R14 checks it |

**Not fixed here (outside this phase's files), reported to the owner:** Phase 20's runner reads
Phase 21 manifests at any depth under `artifacts/phase21-*/`. It needs no change for
`--finalize-abandoned` to unblock it, but any fixture manifest copied under `artifacts/` still
blocks it.

**After the last edit:** the Phase 21 tests gave 88 passed (68 after round 1; 20 added, none removed); the mutation check caught 71 of 71 single-point mutations of the harness (`review-round-2/mutate.out.txt`): the round-1 set re-targeted at the new code (42 of its 46: N05 and N06 retired with the code they mutated, M05 and M06 run together) plus 29 for the round-2 changes. Its first pass caught 70 of 71 (`mutate.first-pass.out.txt`): R29, the served-metadata sign of delivery in `entry_delivered`, survived until a test case was added. The dry plan reproduced the pins above, and its output equals `dry-plan-r2/dry-summary.json`.

Round 2 changed the harness, the tests and this file again. By pitfall 74 these fixes need their
own check before launch (Operator procedure, step 1).

### Closing entry (2026-09-23): round-2 fixes checked; approved for launch

- **Round-2 verification agent:**
  - checked every round-2 finding marked fixed against the code, the tests and this file;
  - re-ran the tests (88 passed) and the dry run, which reproduced plan hash `6d9182b4…`,
    1,063 requests, a $22.2167 bound and pre-check `passed: true`;
  - confirmed every pin equals its file;
  - found no blocker and no major, only 3 text-level minors (M1–M3) that change neither the
    harness nor the plan.
- **The owner (delegated to Claude as PM)** accepts that verification as the check of the
  round-2 changes that step 1 requires, and approves this phase on its own.
- **Order of launch:** after Phase 20's run finishes, never beside it.

