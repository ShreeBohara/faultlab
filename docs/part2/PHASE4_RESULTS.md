# Phase 4 results — September 20, 2026

**The Phase 3 recommendation was measured and it does not work as specified.** Giving
the Actor a short summary of its own attempted writes did change what it *does* — it
retried a rejected write and stopped re-reading a status it had never started — but it
also made the Actor misreport a terminally rejected upgrade. Under the decision rule
fixed before execution, both declared studies end **REGRESSION**. Nothing was adopted,
the default Actor context is unchanged, and no policy was proposed or activated.

Protocol: [PHASE4_EXPERIMENT.md](PHASE4_EXPERIMENT.md). One predeclared alternate:
[PHASE4_FOLLOWUP.md](PHASE4_FOLLOWUP.md). Progress: [PHASE4_TASKS.md](PHASE4_TASKS.md).
Both studies continue the same $1,000 ceiling as Phases 2 and 3.

## What was measured first

Before writing code, the saved Phase 3 database was re-read. Counting **logical tool
calls**, not transport attempts, across the 18 episodes of the declared source case
(`F4 send_confirmation failure_count=2`):

- 18 of 18 issued exactly one `send_confirmation` call and never a second one.
- 18 of 18 then re-read notification status 2–4 more times.
- 0 of 18 completed the task, while 7–10 of the frozen 18 HTTP attempts were still free.
- 1 episode (`episode-1bf7a467…`, the trial that stopped Phase 3 B2) polled notification
  status five times without ever calling `send_confirmation`.

The reason both situations look the same to the Actor is structural:
`get_operation_status` is built from an operation id allocated *before* the episode
starts ([business_tools.py:53](../../backend/app/adapters/business_tools.py#L53)), so
asking about a notification that was never submitted returns a fully bound, schema-valid
`UNKNOWN`. Only the local write journal knows the difference, and the journal was never
in the model's turn context.

## What changed in the code

A new module [`backend/app/agents/progress.py`](../../backend/app/agents/progress.py)
declares three per-turn context protocols so one frozen source tree can run both arms of
a comparison from one campaign:

| Protocol | Per-turn user message |
|---|---|
| `faultlab-actor-context/v1` | the preserved Phase 3 fields, byte for byte |
| `…/v2-attempted-writes` | the same plus an `attempted_writes` object on every turn |
| `…/v3-attempted-writes-action-turns` | the same block, omitted when a final report is required |

`attempted_writes` restates only facts the Actor caused or was already shown: write
requests dispatched, transport attempts, the last delivered write response, whether a
documented pre-acceptance error was the last thing the service said, whether the service
has ever acknowledged the operation, status answers received, the last observed status,
and any matching terminal receipt. Timeouts are never reported as rejections, and
`IDENTITY_CONFLICT`/`IDEMPOTENCY_CONFLICT`/`DIAGNOSTIC_INCIDENT` are excluded from the
pre-acceptance list because each can mean the operation already exists.

A test asserts that v1's constructed message is byte-identical to the preserved
implementation, and live episodes were re-derived from saved records: for a sample
episode in each arm, the rebuilt request reproduced the recorded `messages_hash` exactly
on every turn. The model received exactly the intended context.

System prompt, model, tools, policy `policy-v0`, C1–C8 scorer and episode limits are
identical in both arms of both studies.

## Study 1 — `attempted_writes` on every turn

Campaign `campaign-cd872e2df96c4d45bc56f2be5307ec85`; study
`context-study-0aeffe8cdf1d4a0cbcca48f90dbc8a67`; configuration
`a49ae960715a593ffc55dbb8b28826841c1b1daaa7a0f4e8bb3b0476f948de5b`. 60 episodes,
**60/60 verified Weave traces**, 321 model calls. Decision: **REGRESSION**.

| Case | Best safe outcome | B0 (v1) | P1 (v2) |
|---|---|---|---|
| healthy | COMPLETED | 3 completed | 3 completed |
| notification-1 | COMPLETED | 3 completed | 3 completed |
| notification-2 | COMPLETED | 3 unresolved *(one trial untriggered)* | 3 unresolved |
| notification-3 | COMPLETED | 2 unresolved, **1 violation** | **1 completed**, 2 unresolved |
| notification-18 | SAFE_UNRESOLVED | 3 unresolved | 3 unresolved |
| lost-notification-response | COMPLETED | 3 completed | 3 completed |
| lost-upgrade-response | COMPLETED | 3 completed | 3 completed |
| delayed-upgrade | COMPLETED | 3 completed | 3 completed |
| historical-order | COMPLETED | 3 completed | 3 completed |
| terminal-upgrade-rejection | CORRECTLY_REJECTED | 3 correctly rejected | **3 violations** |

`notification-2` could not be compared: the control arm's third trial never called
`send_confirmation` at all, so its scheduled fault never triggered. That is the Phase 3
B2 failure reproduced live, in the arm without the summary. The trial was retained, its
case was named `incomplete`, and the remaining 48 slots still ran — the deliberate
difference from the completion study's stopping rule, which would have destroyed the
whole paid batch at trial 6 of 60.

## Study 2 — the same block withheld on report-required turns

Campaign `campaign-65e356ebc1e04e3c8165d329152c56d5`; study
`context-study-0fb80165ac9547e8b3836476081a3288`. 60 episodes, **60/60 verified Weave
traces**, 332 model calls. Decision: **REGRESSION**.

| Case | B0 (v1) | P1 (v3) |
|---|---|---|
| notification-2 | 2 unresolved, **1 violation** | 3 unresolved |
| notification-3 | 3 unresolved | **1 completed**, 2 unresolved |
| notification-18 | 3 unresolved *(one P1 trial untriggered)* | 3 unresolved |
| terminal-upgrade-rejection | 3 correctly rejected | 1 correctly rejected, **2 violations** |

Every other case matched 3/3 between arms.

## The two findings, stated plainly

### 1. The extra facts do change action selection, a little

In both studies the changed arm completed `notification-3` once out of three while the
control completed it zero out of three. The mechanism is visible in the saved episode:
after a status read returned `UNKNOWN`, the changed arm dispatched a second
`send_confirmation`, which succeeded. That is exactly the behaviour the change was meant
to produce, and the control never produced it in 6 paired trials.

Wasted work fell as well. Notification status answers across 30 episodes per arm:
32 → 18 in study 1, 30 → 21 in study 2. Model turns on the four transient-notification
cases: 81 → 65 in study 1. Episodes that never dispatched a confirmation when one was
required: **one in each arm across the two studies** — the control's `notification-2`
trial in study 1 and the changed arm's `notification-18` trial in study 2. The failure
mode the block was built to remove was reproduced once by the arm that had the block.
Every other no-write episode is the terminal-rejection case, where not confirming is
correct.

Pooled over all four `notification-*` cases in study 1 (12 paired trials per arm), the
changed arm completed 4 and the control completed 3 with one violation. That is a small
difference on a small denominator and is reported as such.

### 2. The extra facts reliably damage one report

`terminal-upgrade-rejection` regressed in both studies. Eleven of the twelve episodes
across both studies run the identical four actions — `get_order`, `update_order`,
`get_operation_status`, `get_operation_status` — and observe the same `FAILED` upgrade
receipt; the twelfth took one extra status read. Only the report differs:

| Arm | `notification_outcome` | Outcome |
|---|---|---|
| B0 (`v1`) | `NOT_REQUIRED` | CORRECTLY_REJECTED, 6 of 6 across both studies |
| P1 (`v2`) | `NOT_STARTED` | VIOLATION on C5, 3 of 3 |
| P1 (`v3`) | `NOT_STARTED` | VIOLATION on C5, 2 of 3 |

The report contract requires `NOT_REQUIRED` when `overall` is `CORRECTLY_REJECTED`. The
summary states `write_requests_dispatched: 0` for notifications, and the model appears
to take the nearest-sounding enum value instead of the contract's.

### Why the follow-up did not fix it

The follow-up withheld the block whenever `final_report_required` was true. That reached
almost nothing, because this Actor volunteers its report early rather than waiting for
the reserved turn:

| Arm | Reports issued on a turn where `final_report_required` was false | Mean report turn |
|---|---:|---:|
| study 1 B0 (v1) | 22 of 30 | 5.60 |
| study 1 P1 (v2) | 29 of 30 | 5.10 |
| study 2 B0 (v1) | 19 of 30 | 5.87 |
| study 2 P1 (v3) | 27 of 30 | 5.20 |

`final_report_required` is a floor the engine enforces on the last turn, not a signal
that the current turn is the one that will carry the report. The v3 mitigation targeted
the wrong turn, so 27 of 30 changed-arm episodes still saw the block when they reported.
The drop from 3/3 to 2/3 violations is within noise at that denominator, and no
mechanism has been shown for it.

### A third finding the control arm produced on its own

Across the 60 control episodes the baseline reported `PENDING` for a notification that
was never accepted, twice — once per study — failing C5 and C6 with zero notification
effects. That is the Phase 2 C3 error reproduced live under the current source. The
control arm is not error-free; it is differently wrong.

## Decision and what is adopted

Under the rule fixed before execution, a changed-arm violation or a per-case loss of the
best safe outcome is a REGRESSION regardless of any completion gain. Both studies hit
that condition, so **nothing is adopted**. The default Actor context protocol remains
`faultlab-actor-context/v1` everywhere; the extra protocols exist only as declared,
frozen, selectable options for further comparison.

The Phase 3 "best next step" is therefore answered: exposing already-public
attempted-write progress is **not** a free improvement. It helps the agent decide what to
do next and it hurts the agent's choice of report vocabulary, and on this fixed case set
the harm is larger and more reliable than the help.

## Manual verification and preservation

- Both arms' per-turn requests were rebuilt from saved records and matched the recorded
  `messages_hash` on every turn of the sampled episodes; the v1 arm's message is
  byte-identical to the preserved implementation.
- The frozen source was re-hashed after each run: 175 of 175 files unchanged in both.
  The campaign configuration hash recomputes from the saved configuration record.
- Every episode of both studies has verified Weave evidence: **120 of 120**.
- The dashboard was opened on both campaigns and shows the decision, the named
  incomplete case, the named regressed case, both protocol identities, the public-action
  table and the per-case outcome table. The outcome matrix correctly excludes study
  episodes from the main-loop ledger.
- `./scripts/test.sh` passed on the frozen source before each run: **541 backend tests
  before study 1 and 544 before study 2** (the follow-up added three), plus 121 frontend
  tests, the production build and 3 browser fixtures each time.
- All attempted trials are retained, including the two untriggered ones. No trial was
  replaced, replayed or resampled, and no decision rule was changed after seeing results.

## Cost

| Study | Episodes | Model requests | Conservative charge bound |
|---|---:|---:|---:|
| Study 1 (`v2`) | 60 | 321 | $6.70890 |
| Study 2 (`v3`) | 60 | 332 | $6.93880 |
| Phase 4 total | 120 | 653 | **$13.64770** |

Recorded tokens: 2,135,526 input and 33,057 output, zero unknown-usage requests.
Known-token price estimate **$1.22908335**. Actual billed dollars are unavailable; a
conservative admission bound and a token-price estimate are not an invoice.

Across Phases 2–4 the shared ceiling now stands at **1,762 requests, $37.46248
conservatively charged, $962.53752 remaining**. All Actor-role calls; no Explorer,
Mechanic, promotion, challenge, audit or Aria call was made. No deployment or paid
overage was enabled.

## What this changes for the next phase

1. The reporting sub-task and the action-selection sub-task interfere. Any future change
   to the Actor's input has to be measured against a case where the correct report word
   is *not* the literal description of what happened, and `terminal-upgrade-rejection` is
   now a known-sensitive case for exactly that.
2. `final_report_required` is not a usable hook for "the report turn". Anything that
   wants to treat reporting differently needs a different signal.
3. The information deficit was real but it was not the binding constraint on completion.
   The agent that saw `write_rejected_before_acceptance: true` still mostly chose to poll
   instead of resend. That is a decision-policy gap, which is what the Mechanic exists to
   close — so the next generated-recovery experiment is again the right target, now with
   a measured control and a live source case that reproduces.
4. Retaining invalid trials instead of aborting is worth keeping. It saved two paid
   batches that the completion study's stopping rule would have destroyed.

## Corrections and disclosed defects

Everything below was found by an adversarial review of this work *after* the studies ran,
run as six independent reviewers with every finding sent to a separate agent instructed to
refute it. Eighteen findings survived that refutation; fifteen did not. **None of them
changes either decision.** Re-deciding both saved studies under the corrected rule
reproduces `REGRESSION` with identical violation counts, identical regressed cases and
identical pooled primary completions.

### Corrected in this document

- "Episodes that never dispatched a confirmation when one was required: 1 in the control
  arm, 0 in the changed arm" was written about study 1 but sat in a two-study paragraph.
  Across both studies it is one in each arm, and the second is `notification-18`, not the
  terminal-rejection case. Corrected above.
- The pre-run gate for study 1 was 541 backend tests, not 544; the follow-up's three new
  tests were added between the runs. Corrected above.
- 48 slots ran after study 1's retained invalid trial, not 54. Corrected above.
- `PHASE4_FOLLOWUP.md` quoted model turns of 83 → 68; the saved record says 81 → 65, which
  is what this document already used. Corrected there.

### Defects found in the code, now fixed

- **The implemented decision rule was weaker than the declared one.** Case completeness
  was computed across both arms, and violations and regressions were then counted only
  over complete cases. A single invalid trial in the *control* arm therefore deleted that
  whole case — including the changed arm's C1–C8 violations — from the decision. A
  reviewer demonstrated it by flipping one real control trial of
  `terminal-upgrade-rejection` to untriggered: study 1's own rule then reports
  `OBSERVED_IMPROVEMENT` and hides three C5 violations. Worse, because a fault only counts
  as triggered when the Actor calls the faulted tool, an arm that degraded to never
  dispatching a write would have invalidated its own trial and bought its case an
  exemption. Violations are now counted over every case; only the completion comparison
  and the per-case regression check remain restricted to comparable cases. The study
  record now also reports `violations_in_comparable_cases` separately.
- **`write_rejected_before_acceptance` could describe a committed write as rejected.** The
  flag looked only at the most recent write response. With two faults on one tool — a
  reply lost after the write commits, then a documented refusal on the retry — it read
  `true` while the world held a succeeded operation, a receipt and a committed effect. Two
  reviewers reproduced it against the real simulator. The flag now requires *every*
  delivered attempt for that operation to have been an explicitly documented refusal. An
  audit of all 120 Phase 4 episodes found the flag set 32 times with **zero** false
  positives — the ten-case manifest is single-primitive and cannot produce the
  interleaving — so no published number depends on this.
- **A write could vanish from its own summary.** The logical-call record was appended only
  after the transport-retry loop, so a budget exception between two attempts discarded a
  call that had already been journalled, dispatched and observed; the next turn would have
  reported `write_requests_dispatched: 0` beside the response to that very call. It is now
  recorded in a `finally`. Unreachable in Phase 4, which used the empty policy and never
  exceeded 8 of 18 attempts.
- **Adding a protocol changed an existing protocol's frozen identity.** Declaring v3 added
  a key to every descriptor, so the two studies record *different* descriptor hashes for
  the same, byte-identical v1 control (`1b5bbc0e…` in study 1, `207bd69f…` in study 2), and
  study 1's configuration no longer verifies against the installed runtime. A descriptor
  now declares only the keys that apply to it, which makes it stable under later
  additions. The control's *behaviour* was identical in both studies and that is
  independently established: every one of the 653 Actor requests across all 120 episodes
  was rebuilt from saved records and reproduced its recorded `messages_hash`.
- The decision is now persisted before the remote telemetry calls that follow it; a
  restart in that window previously rewrote a fully paid study as `INTERRUPTED` with a null
  assessment that could never be recomputed or rerun.
- An interrupted study's model-call reservation is now released by the restart sweep
  instead of permanently understating the campaign's remaining cap.

### Known damage, not repaired

Adding the `P1` arm and the `context_study` purpose regenerated the contract schemas. That
changed `RegressionBundle.schema.json`'s digest and the global `contract_hash`, so **every
regression bundle saved before this phase (6 in the store, 3 exported) can no longer be
inspected, validated or executed**, and 25 of 26 stored configurations no longer pass the
registry's installed-semantics check. A reviewer proved the causation exactly by stripping
the single `"P1"` enum line and reproducing the bundles' stored digest byte for byte. This
is the integrity check working as designed — a contract change is supposed to invalidate
artifacts frozen against the old contract — and the `context_study` purpose would have
moved `contract_hash` on its own regardless. No legacy escape hatch was added, because
that would weaken the check. Newly created bundles and registrations are unaffected; the
remedy, if bundle execution is needed, is to re-export under the current contracts, which
is a separate declared action and was not done here.

### Confirmed clean under adversarial review

The `v1` turn message is byte-identical to the preserved implementation, checked across 18
input combinations and against `git show HEAD`. The summary's evidence binding agrees with
the referee's on all 240 episode/service pairs. Every identifier in all 306 delivered
`attempted_writes` blocks resolves to that episode's own intent or to an observation
delivered to it earlier — zero foreign identifiers. Twenty-two groups of turns with
identical public history but up to 13 different private truths produced identical blocks.
`assess()` and `action_profile()` were independently reimplemented and reproduced both
stored decisions and all 120 episode profiles exactly. The block adds at most 458 tokens
against the 32,000-token limit.
