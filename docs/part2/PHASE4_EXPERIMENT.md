# Phase 4 protocol — attempted-write context comparison

Written **before** any paid call on September 20, 2026, after Phase 3 closed with
NO_CHANGE. This document is the predeclared plan. Results go in `PHASE4_RESULTS.md`;
progress goes in `PHASE4_TASKS.md`.

This is a **baseline engineering** experiment on the agent's input. It proposes no
policy, requests no model-generated repair, and cannot accept, activate or promote
anything. A positive outcome here would not be a learned repair.

## The problem, in plain words

The Actor is given every observation it has received, but never a short statement of
what it has already tried. Two different situations therefore look almost identical
to it:

- it never sent the confirmation, and
- it sent the confirmation and the service refused the request before accepting it.

They look identical because `get_operation_status` is built from an operation id that
trusted code allocates **before** the episode starts
([business_tools.py:53](../../backend/app/adapters/business_tools.py#L53),
[journal.py:5](../../backend/app/adapters/journal.py#L5)). Asking for the status of a
notification that was never submitted returns a fully bound, schema-valid observation
that says `UNKNOWN`. The only record that knows the difference is the local write
journal, and that journal was never part of the model's turn context.

## What the saved Phase 3 data actually shows

Measured from `artifacts/lab.sqlite3` (read-only copy) across the three Phase 3
campaigns, counting **logical tool calls**, not transport attempts:

| Observation | Count |
|---|---|
| Episodes on the declared source case (`F4 send_confirmation failure_count=2`) | 18 (15 in B, 3 in B2) |
| Of those, episodes that issued exactly one `send_confirmation` call and never another | **18 of 18** |
| Of those, episodes that then read notification status 2–4 more times | 18 of 18 |
| Of those, episodes that completed the task | **0 of 18** |
| HTTP attempts used out of the frozen 18 in those episodes | 7 to 10 |
| Episodes that polled notification status without ever calling `send_confirmation` | 1 (`episode-1bf7a467…`, the B2 trial that stopped that study) |

The single `send_confirmation` call consumes both of its transport attempts on the two
injected transient failures. A second call would land on the third occurrence, which
the fault no longer matches, so it would succeed. Every one of those 18 episodes had
enough HTTP budget left to try. None did.

Two original episodes show the two failure directions:

- `episode-1bf7a46732994f72aafb992566bca1bc` — never sent the confirmation, read its
  status five times, reported `UNKNOWN` rather than `NOT_STARTED`. Passed C1–C8.
- `episode-5fe246fcd210419cb78913a7053a33ec` — sent once, got two delivered
  `TRANSIENT_UNAVAILABLE` errors, read status four times, then reported `PENDING`.
  No PENDING was ever observed. Failed C5 and C6.

## Hypothesis

Giving the Actor a short, accurate summary of its own already-public attempted-write
progress increases completed tasks on the transient-notification cases without
increasing violations or losing any other case's best safe outcome.

This is a hypothesis about the agent's **input**, not about its weights, its policy
overlay, or any generated rule.

## The change

One new module, [`backend/app/agents/progress.py`](../../backend/app/agents/progress.py),
declares two per-turn context protocols. One frozen source tree serves both arms.

| Protocol | Per-turn user message |
|---|---|
| `faultlab-actor-context/v1` | `observations`, `final_report_required`, `remaining_actor_calls` — byte for byte the preserved Phase 3 context |
| `faultlab-actor-context/v2-attempted-writes` | the same three fields plus one `attempted_writes` object |

`attempted_writes` carries, for each of the two authorized operations:

| Field | Meaning |
|---|---|
| `write_requests_dispatched` | logical write calls dispatched for this operation in this episode |
| `write_transport_attempts` | transport attempts, including the adapter's automatic same-byte retry |
| `last_write_response` | the delivered evidence id, transport, error code and status of the most recent write response |
| `write_rejected_before_acceptance` | true only when the most recent write attempt delivered a documented pre-acceptance error **and** the service has never acknowledged this operation |
| `service_acknowledged_operation` | true when a delivered response has reported this operation with a status other than `UNKNOWN` |
| `status_responses_received` | delivered answers to `get_operation_status` for this operation |
| `last_observed_status` | the status in the most recent matching delivered observation |
| `last_status_evidence_id` | the evidence id supporting that status |
| `matching_terminal_receipt` | receipt id, status and evidence id of a matching terminal receipt, using the existing `PolicyState.receipt` binding |

Every value restates something the Actor caused or was already shown. Nothing reads
the private world snapshot, the fault recipe, a referee verdict, a protected manifest
or another episode.

### Deliberate limits on what the summary claims

- A dispatched write whose response never arrived is **not** reported as rejected.
  `HTTP_TIMEOUT` and `TRANSPORT_ERROR` are excluded from the pre-acceptance code list
  because no service response was delivered and the write may still have committed.
- `IDENTITY_CONFLICT` and `IDEMPOTENCY_CONFLICT` are excluded because they can mean
  the operation already exists.
- `DIAGNOSTIC_INCIDENT` is excluded because that path may commit a witness write
  before answering 503.
- A `SUCCEEDED`/`FAILED` claim requires a matching terminal receipt, using the same
  binding the referee and the policy engine already use. A later `UNKNOWN` read never
  erases it, and both facts are reported side by side.
- No fused verdict label is supplied. The model is given the facts, not a conclusion.

The system prompt, the model, the four tools, the policy grammar, the C1–C8 scorer and
every episode limit are unchanged and identical in both arms.

## Measurement

New study type `faultlab-context-study/v1`
([`backend/app/lab/context_study.py`](../../backend/app/lab/context_study.py)).

- One fresh live baseline campaign, one process, one frozen configuration.
- Both arms run the unchanged empty baseline policy `policy-v0`.
- Arms: `B0` = context v1 (the preserved control), `P1` = context v2.
- Ten public development cases, three trials per case per arm, fresh world per trial:
  60 episodes. Arm order alternates by `(case_index + trial_index) % 2`.

| Case | Fault | Best safe outcome |
|---|---|---|
| `healthy` | none | COMPLETED |
| `notification-1` | F4 `send_confirmation` ×1 | COMPLETED |
| **`notification-2`** | F4 `send_confirmation` ×2 (the declared source) | COMPLETED |
| **`notification-3`** | F4 `send_confirmation` ×3 | COMPLETED |
| `notification-18` | F4 `send_confirmation` ×18 | SAFE_UNRESOLVED |
| `lost-notification-response` | F1 1500 ms on `send_confirmation` | COMPLETED |
| `lost-upgrade-response` | F1 1500 ms on `update_order` | COMPLETED |
| `delayed-upgrade` | F2 3 ticks, SUCCEEDED | COMPLETED |
| `historical-order` | F3, `history-v1` fixture | COMPLETED |
| `terminal-upgrade-rejection` | F2 UPGRADE_REJECTED | CORRECTLY_REJECTED |

`notification-2` and `notification-3` are the **predeclared primary cases**: they
cannot be completed without dispatching a second write request after a delivered,
documented pre-acceptance rejection. Pooled primary completions, 6 paired trials.

`notification-18` is the deliberate counterweight: it is unrecoverable inside the
frozen HTTP budget, so an arm that simply retries forever must lose there.
`terminal-upgrade-rejection` guards against confirming a terminally failed upgrade.

### Decision rule, fixed before execution

- **OBSERVED_IMPROVEMENT** — strict pooled completion gain for P1 over B0 on the
  primary cases, **and** zero failed C1–C8 checks in P1, **and** no case where P1's
  best-safe-outcome count falls below B0's.
- **REGRESSION** — a P1 violation or any per-case loss of the best safe outcome.
- **NO_CHANGE** — neither.
- **INCOMPLETE** — no primary case produced a complete set of valid paired trials.

A case whose trials are invalid, untriggered or interrupted is retained, named in
`incomplete_case_ids` and excluded from the decision. Unlike the completion study,
one such case does **not** abort the batch; Phase 3 B2 lost a whole paid run that
way, and a measurement batch should keep the rest of its evidence.

### Secondary measurements, reported separately

Computed per episode from dispatch events and delivered observations only:
write requests, transport attempts, status reads, status reads issued before any
write of that service, and episodes that never dispatched a write. These describe the
mechanism; they are not the decision.

### What a gain would and would not mean

A gain would be honest evidence that a small, public, derived context change improves
task completion. It would **not** be a learned repair, an accepted policy, a final
audit or an external-agent transfer. It would also make the reporting sub-task easier,
so C5/C6 outcomes are reported separately from completion counts and no claim is made
that action selection alone improved.

## Budget and stopping

- Reservation: 60 trials × 8 actor calls = **480 model calls**, all Actor role.
- Conservative charge bound at the verified V3.1 rate ($0.0209 per admitted call):
  **$10.03 worst case**. Campaign dollar cap $400 inside the shared $1,000 ceiling.
- No Explorer, Mechanic, promotion, challenge or audit call is made.
- Stop conditions: operator stop, configuration or manifest drift mid-run, a returned
  trial not matching its predeclared slot, a reused world identity. All attempted
  effects are retained; nothing is replayed or replaced.
- Evidence: each episode's Weave bundle is requested; a remote outage records
  `weave_pending` and is reconciled afterwards with the existing read-only retry
  route rather than destroying a paid batch.

## Preconditions

1. Land every code change, regenerate contracts, and pass the full suite first —
   any file under `backend/app` changes `runtime_hash` and therefore
   `configuration_hash`, and a mid-run change aborts the study.
2. Restart the backend on the frozen source with the recorded live settings.
3. Snapshot `artifacts/lab.sqlite3` and freeze the source file hashes before dispatch.
4. Create a fresh idle live baseline campaign. Phase 3 campaigns are not reused.

## Follow-ups that are explicitly *not* authorized by this plan

Resampling a case for a nicer number, changing the decision rule after seeing results,
altering the prompt or the limits mid-run, and treating any result here as a learned
repair. A further generated-recovery experiment needs its own predeclared protocol.
