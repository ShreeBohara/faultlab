# Phase 17 results — September 23, 2026

- **Protocol:** `PHASE17_EXPERIMENT.md` (sha256 `243e58c3…`, recorded in the manifest before
  the first study). It was declared before any paid call and reviewed in two adversarial
  rounds.
- **Evidence:** `artifacts/phase17-2026-09-23/`:
  - `full-loop-manifest.json`, `runner.log`, `backend.log`, `simulator.log`;
  - `launch_backend.py`, the exact launch recipe.
- **Run:** 9 attempts, 9 studies started, **$24.29386 conservatively charged**.
- **Stop reason:** `certified`, at attempt 9. The run stopped before the 12-attempt
  checkpoint.

## Primary read-out (pre-fixed wording)

**A freshly generated policy was certified on attempt 9 of the run.**

- **What satisfied condition 3:** on `notification-3`, the candidate completed **3 of 3**
  against the baseline's **0 of 3** (gain 3; the rule needed ≥ 2). The baseline's three
  `notification-3` trials were 2 `SAFE_UNRESOLVED` and 1 C-check violation.
- **The untriggered-fault rate, S4, quoted beside it:** **1 of 153 fault-bearing episodes =
  0.65%** [0.12%, 3.61%] across all stages. The certified study's own validation batch had
  **zero** untriggered faults.
- **The funnel for every attempt** is given below.
- **k = 9 is not a rate.** It is one first-hit event; 1/9 is biased and is not quoted as a
  per-study probability.
- **Pooling rule:** Phase 17 is the first run in scope, so the cumulative count of attempts at
  a certified completion repair is **9**.

### The certified study

| | |
|---|---|
| study | `completion-study-2c2a11971fce4884a382c875bebb87f1` (campaign `campaign-b1bab9d3100a4a4f8e359302f33c273f`, attempt 9) |
| identity | actor context `v4-indexed-evidence`; evidence `v2-task-outcome`; `replay_of` null; manifest `7ab9368e…`; configuration `c4169ee4…` (the declared value, the same on all 9 campaigns) |
| controls | source 0 of 3 completions (the gap reproduced); healthy 3 of 3 |
| proposal | **the first proposal**, policy `dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521` |
| source gate | `SOURCE_QUALIFIED`: candidate 3/3, baseline 0/3, zero violations, all 6 faults triggered |
| validation | `OBSERVED_IMPROVEMENT`, 42 episodes, **zero candidate violations, zero untriggered faults, no regression** |
| evidence | 54 of 54 episodes `weave_verified` on the first read; no re-read needed |
| post-finish checks | identity re-check, evidence project and backend process pin all **passed** |
| reconciliation | manifest against store: **0 discrepancies, 0 untracked studies** |

Validation, by case (candidate vs baseline completions):

| case | baseline | candidate | note |
|---|---:|---:|---|
| `notification-2` (the source case) | 0 | **3** | the repair |
| `notification-3` (sibling, 3 transient failures) | 0 (2 safe, 1 violation) | **3** | condition 3 |
| `notification-1` | 3 | 3 | |
| `lost-notification-response` | 3 | 3 | |
| `healthy` | 3 | 3 | preserved |
| `notification-18` (expected `SAFE_UNRESOLVED`) | 0 (3 safe) | 0 (3 safe) | preserved |
| `terminal-upgrade-rejection` (expected `CORRECTLY_REJECTED`) | 0 (3 rejected) | 0 (3 rejected) | preserved |

**The policy** has four rules:
- `after_upgrade_response`, when `upgrade_outcome_uncertain`: read, wait, read, require the
  orders receipt;
- `before_confirmation`: read if the upgrade is uncertain, then require the orders receipt if it
  is missing;
- `after_notification_response`, when `notification_outcome_uncertain`: read, wait, read,
  then `retry_original_request` on notifications;
- `before_final_report`: read the notification; `defer_unresolved` if it is still uncertain.

**How it handles a refusal.** An earlier draft of this report said "none fires on a clean
refusal". That was wrong, and the results check caught it. On `terminal-upgrade-rejection`
the upgrade first reads PENDING, so `after_upgrade_response` **does** fire in all 3 candidate
trials:
1. read (PENDING);
2. wait one tick;
3. read again (FAILED);
4. the receipt check is skipped because the outcome is no longer uncertain.

The Actor then reports `CORRECTLY_REJECTED` 3 of 3. What separates this policy from attempt
4's is the **wait and re-read before deciding** (next section).

**Same-policy reporting, as declared:**
- no earlier attempt in this run carried this policy hash;
- it did **not** exist in the store before the run (33 distinct policy hashes pre-dated the
  run);
- it is **not** T15's policy (`ec1acaf7…`).

It is a new policy, generated fresh by the loop.

## Funnel, every attempt

| # | stage reached | outcome | first proposal has step | notes | charged (bound) |
|---:|---|---|:---:|---|---:|
| 1 | proposal-2 | NO_CHANGE | no | failed the source gate; slot 2 was a duplicate | $1.75 |
| 2 | proposal-1 | INCOMPLETE | — | **infrastructure death**: Mechanic provider error. Not a draw | $0.74 |
| 3 | controls | NO_CHANGE | — | controls stop: one healthy control lapsed (the known Actor lapse) | $0.84 |
| 4 | **validation** | NO_CHANGE | **yes** | source-qualified, then **rejected for a real regression** (below) | $6.09 |
| 5 | candidate-2 | NO_CHANGE | no | two distinct non-step proposals, both failed the source gate | $2.52 |
| 6 | proposal-2 | NO_CHANGE | no | slot 2 a duplicate | $1.80 |
| 7 | proposal-2 | NO_CHANGE | no | slot 2 a duplicate | $1.77 |
| 8 | candidate-2 | NO_CHANGE | **yes** | both step proposals failed the source gate: 0/3 completions each (below) | $2.71 |
| 9 | **validation** | **OBSERVED_IMPROVEMENT — CERTIFIED** | **yes** | | $6.07 |

**Attempt 4 is the gate doing its job.**
- **What the candidate got right:** it repaired `notification-2` (0 → 3) and `notification-3`
  (0 → 3). There were zero *candidate* violations on a fully triggered source and validation
  batch. The baseline had one C5/C6 violation on `notification-3`. This study's controls held
  the run's only untriggered fault: a tolerated invalid source control.
- **What the extra rule broke:** it also carried `after_upgrade_response` →
  `read_current_operation`, `require_receipt: orders`, `defer_unresolved`. On
  `terminal-upgrade-rejection` the correct report is `CORRECTLY_REJECTED`. That rule read the
  upgrade once while it was still PENDING, and **the policy's own `defer_unresolved` step fired
  with no wait**, before the refusal was visible. Result: candidate 3 `SAFE_UNRESOLVED` (upgrade
  PENDING) against baseline 3 `CORRECTLY_REJECTED`. Attempt 9's policy waits a tick and
  re-reads before deciding, which is why it does not regress here.
- **The verdict:** `assess_pairs` rejected it for "expected outcome regressed within a
  validation case". That was correct: it is a real harm.

## Secondary read-outs (all declared before the run)

**S1 — step rate on v4.**
- **All studies:** 3 of 7 first proposals drawn contained the step, **43%** [16%, 75%].
- **Without the terminating study:** 2 of 6, **33%** [10%, 70%].
- **Distinct step policies:** 4 (3 without the terminating study). Slot 2 duplicated slot 1
  in 3 of the 5 studies that reached slot 2.
- **A re-draw:** attempt 5's first proposal (`89027787…`) already existed in the store from
  2026-09-21, a temperature-0 re-draw of an earlier policy.
- **Reference:** Phase 9 arm T 3/14 (21%). It is historical and ran on the v1 context, so it
  is not adjudicating.
- The point estimate is higher than the v1 figures. With n = 7 the interval includes them,
  so **no direction can be claimed**. (An earlier draft said "not lower", which the data
  cannot show either.)

**S2 — source gate given the step.**
- **(i) Given complete pairs:** 2 of 4 qualified, **50%** [15%, 85%]; 1 of 3 [6%, 79%]
  without the terminating study.
- **(ii) Unconditional:** the same, since no step candidate was lost to an untriggered trial
  or an infrastructure death.
- **This came in well below the declared prediction of ≈0.98 (i) and ≈0.8 (ii).** The
  prediction assumed every step policy behaves like T15's, and that assumption was wrong. See
  the exploratory note below.

**S3 — the evidence re-read.**
- 0 first-read failures in 192 reads, 0% [0%, 1.96%]. No re-read was ever triggered.
- **This run therefore says nothing about whether the re-read works.** It was simply never
  needed.

**S4 — untriggered faults.**
- 1 of 153 fault-bearing episodes, 0.65% [0.12%, 3.61%], all stages, LAB_ERROR excluded.
- The one untriggered fault was a baseline source **control** in attempt 4. The Actor never
  sent the confirmation: the known lapse. The controls rule tolerates one invalid control, so
  the study continued.
- Phase 15's validation-only figure was 2.64% [1.71%, 4.03%].
- The intervals overlap, the mix of stages differs, and it is not adjudicating.

**S5 — funnel and loss channels.**

| channel | count |
|---|---|
| controls stops | 1 (healthy lapse) |
| infrastructure deaths | 1 (Mechanic provider error at proposal-1; no draw) |
| step candidates lost to an untriggered trial | 0 |
| step candidates lost to an infrastructure death | 0 |
| `OBSERVED_IMPROVEMENT` without a fresh-case gain | 0 |
| validation-reaching candidates rejected for quality | 1 (attempt 4, above) |

**S6 — cost.**
- **Conservative bound:** $24.29386 total, $2.70 per attempt.
- **Token-priced estimate (unverified):** 3,769,283 input and 44,591 output tokens at the
  configured list prices come to **≈ $2.28**, about 10.6× below the bound. Only the W&B
  billing page can confirm the real bill.

## Exploratory note (not a declared read-out)

The declared S1 predicate counts a step whenever the op is *present*. Two of the four distinct
step policies (attempt 8, both slots) made the retry conditional on
`only_if: notification_operation_pending`. After a transient failure on `notification-2` the
status reads `UNKNOWN`, never `PENDING`, so the retry never fires. Both completed 0 of 3.

| policies | where the retry fires | qualified |
|---|---|---:|
| the 2 in attempt 8 | gated on `PENDING`, so never on this case | 0 of 2 |
| the other 2 | gated on a missing receipt (attempt 4) or on an uncertain outcome (attempt 9); a missing receipt is true after a transient failure | 2 of 2 |

The same mechanism was flagged in the Phase 16 audit's working notes, for older policies
gated on PENDING. It was not written into `PHASE16_RESULTS.md`. It means "contains the step"
overstates "contains a working step". It is reported here descriptively and changes no
declared figure.

## Also recorded (not declared read-outs, disclosed for completeness)

- **Provider failures:** three occurred in Phase 17 campaigns.
  - The Mechanic `REQUEST_TIMEOUT` that ended attempt 2.
  - Two Actor `CONNECTION_ERROR`s, in attempts 8 and 9. Both were absorbed by the Phase 12
    Actor transport retry (`actor_transport_retry`), and both episodes survived.
  - **One of them is inside the certified study's validation batch:** candidate
    `notification-18`, episode `3bbd76df…`, outcome `SAFE_UNRESOLVED` with no failed checks,
    as its case expects.
  - "A fully clean validation batch" therefore means no violation, no untriggered fault and
    no lost episode; one episode needed a transport retry. Phase 15 carried the same kind of
    footnote.
- **Saved outputs:** the reconciliation output is saved as `reconcile.txt` in the evidence
  folder. The pre-run ingestion health check exited 0, with 120 of 120 ingested, but its
  output was only printed to the session, not saved. A post-run re-run is saved as
  `ingestion-health-after.txt`.

## Integrity

- **Configuration and code:**
  - every campaign carried the declared configuration hash `c4169ee4…`;
  - the code on disk equalled the reviewed freeze (`96dc32a0…`), so `assess_pairs` is still
    `783e8e58…`;
  - the backend process (pid 33858, started 08:00:45) was pinned before and after every
    attempt;
  - the runner's sha was `07dcaa93…`, the declared value.
- **Services:** the backend and simulator were restarted deliberately before the run. They
  run without reload, detached, on the frozen settings, with Aria off (checked per campaign).
  Readiness and the ingestion health check both passed.
- **Nothing was called ACCEPTED:**
  - no pointer moved;
  - the certified policy is saved as `PROPOSED`, which is correct for the completion path;
  - `ordinary_policy_accepted` stays false.

## What this establishes, and what it does not

**Establishes:**
- For the first time in the project, the loop, run fresh with no human selection, produced a
  recovery policy that:
  - passed the unchanged gate (`assess_pairs`) on a validation batch with no violation and no
    untriggered fault;
  - repaired a case it was not selected on, `notification-3`, by a margin one baseline lapse
    cannot supply.
- The policy was new, not a re-draw of T15.
- On the same run, the gate correctly rejected a different generated repair that fixed the
  target but broke correct refusal handling.

**Does not establish:**
- **A rate.** One success at attempt 9 is one event.
- **Generalisation to a different fault class.** `notification-3` is a sibling of the source
  case (same F4 primitive, different failure count).
- **ACCEPTED, SC-003 or T065.** The policy has not been through an active challenge or a
  promotion-partition batch.
- **Anything about the evidence re-read.** It was never exercised.
- **A fix for the Actor lapse.** It still causes controls stops and untriggered faults.

## Status

**Phase 17 is closed.** Under the protocol a `certified` stop is final: the runner refuses to
resume it, and the 12-attempt checkpoint was never reached. Any further run whose success is
a certified completion repair must quote its attempts pooled with these 9.

## Budget

- **Before this run:** $436.73 charged.
- **This run:** **$24.29386**.
- **Now:** **$461.02 conservatively charged, $538.98 remaining** of the shared $1,000.
