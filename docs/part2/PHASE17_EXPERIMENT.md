# Phase 17 protocol — the first full-loop run on the fixed setup

**Status: declared before any paid call. Revised after two adversarial review rounds.**
Round 1 used five lenses and round 2 three; every blocking finding was attacked by an
independent skeptic. See the review log at the end. No money may be spent until the user
approves this document.

## The question

Can the loop run fresh with no human selection and produce a policy that:
- passes the unchanged gate, and
- clearly improves a case it was not selected on?

The loop is controls → Mechanic proposal → source gate → validation.

It has never happened. 0 of 40 full studies reached `OBSERVED_IMPROVEMENT`, and only one
reached validation. All 40 ran before the Phase 11 citation fix, on the v1 Actor context.
Of the 5 step-containing candidates:
- 3 failed the source gate on a candidate-arm C6 citation error;
- 1 was lost at the source gate to a fault that never fired;
- the one that qualified (T15) later failed validation on a C6 citation error.

No full study has run since 2026-09-21 03:23.

## Success, declared now: a "certified completion repair"

A study is **CERTIFIED** when every one of these holds:

1. **It is a full study on the declared setup:**
   - `replay_of` is null;
   - `actor_context_protocol` = `faultlab-actor-context/v4-indexed-evidence`;
   - `evidence_protocol` = `faultlab-compact-evidence/v2-task-outcome`;
   - `manifest_hash` = `7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483`.
2. **The study's decision and its validation assessment are both `OBSERVED_IMPROVEMENT`** under
   the unchanged `assess_pairs`. That already requires:
   - 3/3 candidate and 0/3 baseline completions at the source gate;
   - zero candidate check failures in the source and validation batches;
   - no per-case regression;
   - healthy and source completions preserved in validation;
   - a strict total gain.
3. **A clear gain off the source case:** on at least one validation case **other than
   `notification-2` (the source case) and `healthy` (the control)**, `L completed − B0
   completed ≥ 2`. It is counted per case and never summed across cases.

**Why condition 3, and why ≥ 2.** Without it the unchanged gate can pass on the source case
alone. `notification-2` is in the validation set, the baseline was selected to fail it, and
the candidate must complete it 3 of 3, so a total gain is automatic. A gain of 1 is not
enough either, because a single baseline lapse can supply it:
- baseline completion is 80/81 on `lost-notification-response`;
- baseline completion is 2/81 on `notification-3`.

Review round 2 computed this exactly, from the stored baseline rates, for a policy that
fixes only the source case and still passes the gate:
- at "≥ 1" it would be certified about **11%** of the time;
- at "≥ 2", about **0.2–0.3%**.

All 17 stored `OBSERVED_IMPROVEMENT` assessments meet "≥ 2": 16 at L 3 vs B0 0 and one at
L 3 vs B0 1, all on `notification-3`. A test pins those 17 by study id. **All 17 are replays
of one policy (T15's).** So "no power lost" holds for that policy and is assumed, not shown,
for others.

**Honest scope of condition 3:**
- In practice the case is `notification-3`. It uses the same fault primitive (F4, transient
  failures on `send_confirmation`) as the source case, with a different failure count, so it
  is a sibling case, not a different fault class.
- `notification-18` (expected `SAFE_UNRESOLVED`) and `terminal-upgrade-rejection` (expected
  `CORRECTLY_REJECTED`) are included in the rule, but a completion gain there is not
  realistically possible.

**What certification is not:**
- it is not ACCEPTED;
- no pointer moves and nothing is activated;
- it does not satisfy SC-003, T065, FR-017 or FR-041 as written, which require an invariant
  repair, an active challenge and a promotion-partition batch.

A route from a certified repair to ACCEPTED would be its own phase, declared and reviewed
before its data exists.

## What is unchanged

| | value |
|---|---|
| gate | `assess_pairs`, text sha256 `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2`, text- and AST-identical to Phase 15 |
| cases | `case_manifest()`, `manifest_hash` `7ab9368e…4483`: 7 cases × 3 trials × 2 arms |
| study shape | 6 controls (one invalid control of each kind is tolerated), 2 proposal slots, 3-pair source gate per distinct candidate, one 42-episode validation, all single-shot |
| referee | `scorer_hash` `19de811c96473eb4…` (`checks.py` is not read by any person or agent; tools hash its bytes) |
| Actor | `deepseek-ai/DeepSeek-V3.1`, `actor_prompt_hash` `12eabe7f41028c05…` |
| Mechanic | `deepseek-ai/DeepSeek-V4-Pro-0813`, temperature 0; `completion.md` unchanged since Phase 6B; `source_hash` `da80ac6fa6e1affb…` unchanged |
| evidence shown to the Mechanic | `v2-task-outcome`, as in Phase 8 and Phase 9 arm T |
| settings | identical to Phase 15: models, per-call bounds ($0.0209 Actor, $0.04984 V4), the $400 per-campaign cap and the request settings. Proven by rebuilding Phase 15's stored configuration `21df22de…` with only the two code hashes swapped, which gives exactly the expected hash below |

## What changed, declared

1. **Actor context v4 in a full study, for the first time.** This changes the Actor's
   episodes. It also changes the control evidence the Mechanic reads, so **the Mechanic's step
   rate under v4 is unmeasured (n = 0)**. Every v1-era rate below is a reference, not a
   prediction that must hold.
2. **In-study evidence re-read (Phase 16).**
   - It fires only when a read ends `RETRYABLE_ERROR` with `DEADLINE` or `TRANSPORT`, at most
     once per episode, and it is blind to arm, outcome and stage.
   - It restarts a telemetry worker that is dead, or alive but never initialized, then
     re-uploads the saved local trace and reads once more.
   - It never retries an integrity failure. Each first failure and its result (VERIFIED,
     FAILED, DENIED or ERROR) is recorded in the study's `evidence_rereads`.
   - Two label limits, both safe (the study ends either way):
     - an integrity conflict found *during* the re-upload surfaces as a generic telemetry
       error and is labelled FAILED, not DENIED;
     - a backend shutdown during a re-read leaves the entry at ATTEMPTED.
   - It cannot change a verdict: the trial and verdict are saved before the read.
   - For a re-read episode, `weave_verified` means the saved local copy was delivered
     afterwards and read back consistent with the local observations and report, not that the
     live capture succeeded. Only `evidence_rereads` tells the two apart.
   - A worker restart also restores live tracing for the rest of the study. The W&B
     *evaluation mirror* for the rest of that stage is lost; that is harmless to every gate.
   - A re-read can take up to ~140 s per episode. There is no per-study cap beyond the
     90-minute study timeout.

**Integrity pins.**
- **Hard-coded in the reviewed runner:** the freeze file sha, the expected configuration
  hash, the settings file sha and `gate_freeze.py`'s sha. The runner refuses to start if a
  typed flag or a file differs from them.
- **Checked by the runner:** the code on disk against the freeze, and `assess_pairs`, before
  any study; the configuration hash at the first campaign, at $0.
- **Recorded in the manifest:** the runner's own sha and this protocol's sha. Resume refuses
  if either changes.
- **Checked by the operator (step 7a):** the runner's own sha, against the table below.

| | value |
|---|---|
| reviewed code freeze | `artifacts/phase16-2026-09-22/gate-freeze-after.json`, sha256 `96dc32a05d7e715c9752aa7837f1593c967efc02df975a332dea3e5f45faa20f`. The code on disk must equal it exactly |
| `algorithm_hash` / `runtime_hash` | `8d92e0c5b7dc5c1f…` / `485c5e1243407367…` (moved from Phase 15's `c59cacf5…` / `b1c765b4…`, as declared) |
| expected `configuration_hash` | `c4169ee49deb7fb27ac44205d6e74b4f89912d1b43bf945636745b1872110418`. The first campaign must equal it before any study starts, at $0 |
| settings file | `artifacts/phase16-2026-09-22/settings-phase17.json` (byte copy of the Phase 9 file), sha256 `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| runner | `scripts/experiments/run_full_loop.py` sha256 `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342` |
| `gate_freeze.py` | `5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190` (hard-coded in the runner) |
| read-out script | `scripts/experiments/phase17_readouts.py` sha256 `a2de5b00879bb170cb77a96126f10abc35df545fd799a0a2b1e980c9022408c6`. It computes S3–S5 exactly as declared; run on Phase 15's studies it reproduces 20/759 and 7 first-read failures in 914 reads |

If any reviewed file changes after this point, the freeze, these values and the review log
must be updated **before** the run. They are never regenerated to get past a mismatch.

## Primary read-out

**Sequential, declared in advance: the run stops at the first CERTIFIED study.** The primary
is whether one occurs, and at which **attempt**. Attempt numbers count every attempt,
including a campaign-create or study-start failure that ran no study. Every attempt is in
the denominator. The number *k* is never converted into a per-study rate (1/k is biased).

Pre-fixed wording (none may be reworded afterwards):
- **Success:** "A freshly generated policy was certified on attempt *k* of the run." Always
  given with the full funnel, S4 and the gain that satisfied condition 3.
- **No success at the attempt cap or the spend guard:** "No certified repair in *N*
  attempts", followed by where each study stopped.
- **Breaker or other abort:** "The run stopped after *N* attempts because *reason*; no
  certified repair up to that point". That is not a finding about the loop.
- **User stop at the checkpoint:** "Stopped by decision at the checkpoint after *N*
  attempts", with the funnel.

**An abort after a finished study (declared now).** The primary is read from the attempt
rows, not from the run's stop reason.
- **(i) Not certified.** A study that met conditions 1–3 but then failed a post-finish check
  in the same attempt is not certified. The checks are: the identity re-check, any verified
  evidence row naming another project, and the backend-process pin. These are part of
  condition 1: stricter, never looser. The runner sets `certified: false` and records
  `post_checks: failed …` on that row.
- **(ii) The success at attempt *k*.** A study that met conditions 1–3 on the record seen the
  moment it finished, and then the runner aborted for another reason, **is** the success.
  Those reasons are: the idle wait, a transport error on the re-read, a signal, or the
  process going away. Its row shows `post_checks: pending`, and it is reported with the
  success wording followed by "the runner then aborted: *reason*".
  - If the row is recovered on a later resume, the identity and evidence-project checks are
    re-run. The process pin cannot be re-checked, and the report says so.

**Same policy drawn twice.** At temperature 0 the Mechanic can draw an identical policy in
several studies, and each such study tests it afresh. That is part of the loop. It is counted
and never excluded. Any certification is always reported with:
- the certified `policy_hash`;
- every earlier attempt in this run whose candidates carried it, with their decisions (the
  runner records this);
- whether that hash already existed in the store before the run, T15's
  `ec1acaf76e74…` in particular. That is a read-only query at report time.

**Prediction.** Per-study probability = P(controls pass) × P(step in the first proposal) ×
P(source gate | step) × P(validation accepts) × P(condition 3 | accepts).

| factor | value used | basis |
|---|---|---|
| controls pass | ~0.87 | v4 baseline source leak 1/187; healthy lapse ~2.5%/episode; infrastructure |
| step in the first proposal | 0.18 | v1 era: 5/28 V4 first proposals; 4/15 on the closest setup. **Unmeasured on v4**, so the lower plausible bound is ~0 |
| source gate given the step | ~0.8 | if the step policy behaves like T15's: 184/184 valid v4 source completions, 6/190 untriggered |
| validation accepts | ~0.32 | Phase 15: 9 of 28 per attempt |
| condition 3 given acceptance | ~1.0 | 17 of 17 stored |

Central **~0.04 per study**. Two caveats:
- **The source and validation factors come from one policy (T15's).** Other step policies
  carry other rules and have never been validated.
- **The controls × source product (0.70) runs ~10% above the audit's empirical 0.62–0.65.**
  That is roughly offset by using 5/28 rather than 4/15.

| attempts | P(≥1 certified) at p = 0.02 | 0.04 | 0.06 | 0.09 |
|---:|---:|---:|---:|---:|
| 12 | 0.22 | 0.39 | 0.52 | 0.68 |
| 30 | 0.45 | 0.71 | 0.84 | 0.94 |
| 60 | 0.70 | **0.91** | 0.98 | 1.00 |

## Operator checkpoint after 12 attempts (no paid work past it without the user's approval)

The run pauses after 12 attempts (`--stop-after 12`). I then:
- reconcile the manifest against the store;
- report the funnel to the user;
- recommend continuing unless one of these holds:
  - **(a)** at least 10 first proposals were drawn, none contained the step, and nothing
    source-qualified;
  - **(b)** infrastructure deaths are ≥ 50% of attempts;
  - **(c)** conservative spend per attempt exceeds $4.40 (2× the prediction). This mostly
    fires when many studies reach validation, which would be upstream success, and I will
    say so if it happens.

**Rule (a) is a spend decision, not a finding.** Even with no change from v1, 0 of 10 happens
~14% of the time at a step rate of 0.18 (0.82¹⁰), and 39% at 0.09. The draws are correlated
at temperature 0, so the real chance is higher still. If (a) fires, the report says: "*k* of
*n* first proposals contained the step (Wilson 95% upper bound *U*; *d* distinct policies).
This justifies stopping this design; it is not evidence that the rate fell."

The user decides. A pause cannot manufacture a success, because success is a first-hit event
and every attempt stays in the record.

**There is exactly one checkpoint.** A continuation is `--resume --stop-after 60` with every
pin, which runs to the attempt cap, the spend guard, the breaker or the first certified
study. The runner requires `--stop-after` in every live session, so no session can
silently run without a declared stop.

## Secondary read-outs, all declared now

Stop-at-first-success biases S1 and S2 upward, because the terminating study always has the
step and qualified. **S1 and S2 are therefore reported both with and without the terminating
study, as a bracket.** Without it the figures are biased the other way, because they
condition on non-certification. The runner computes both.

- **S1 — step rate on v4.**
  - Definition: step-containing first proposals ÷ first proposals drawn, using the Phase 9
    predicate (`retry_original_request` with `service: notifications` at
    `after_notification_response`).
  - Phase 9 rule: a refusal or an invalid output counts as a draw without the step; "no
    proposal requested" is no draw.
  - Also reported: distinct step policies (temperature 0 makes draws correlated) and slot-2
    duplicates.
  - Reference: Phase 9 arm T, 3/14. It is historical and ran on another Actor context, so it
    is **not adjudicating** (pitfall 31).
- **S2 — source gate given the step, as two declared numbers.**
  - **(i) Given complete pairs:** qualified ÷ step candidates whose source pairs were
    complete. Reference 1/4 under v1. Predicted ≈ 0.98 if the step policy behaves like T15's.
  - **(ii) Unconditional:** qualified ÷ all step candidates tested. Reference 1/5 under v1.
    Predicted ≈ 0.8. Losses to untriggered trials are counted under S5.
- **S3 — the evidence re-read.** Reads, re-reads by result, and the first-read failure rate
  per episode. Computed by `phase17_readouts.py` as declared above. If a re-read never
  recovers anything, I say so.
- **S4 — the nuisance, quoted beside every validation result.**
  - Definition: the untriggered-fault rate per fault-bearing episode across **all stages
    (controls through validation), excluding LAB_ERROR episodes**, with a Wilson interval,
    computed by `phase17_readouts.py`.
  - Reference: Phase 15 validation only, 20/759 = 2.64% [1.71%, 4.03%].
- **S5 — funnel and loss channels.** It reports:
  - controls stops by rule (one invalid control of each kind is tolerated there, so
    "untriggered is fatal" applies to the `assess_pairs` gates, not to controls);
  - infrastructure deaths by `error_type`;
  - step candidates lost to an untriggered trial, **and step candidates lost to an
    infrastructure death** (these drop out of both S2 figures, so they are counted here);
  - a provider death during proposal-1: not a draw, because no candidate is recorded;
  - **every `OBSERVED_IMPROVEMENT` that failed condition 3**, stated prominently: it passed
    the unchanged gate but is not certified.
- **S6 — cost.** The conservative bound per attempt. The token-priced estimate is reported
  separately and labelled unverified.

**Pooling rule (scope defined before any data).**
- **What it covers:** every later run, under any phase name and with any parameters, whose
  success criterion is a certified completion repair (conditions 1–3, or a stricter version).
  Changing the cap, headroom, breaker, checkpoint, pins, Actor context, prompts or models does
  not take a run outside it.
- **What each such report gives:**
  - (i) that run's own "attempt *k* of *N*";
  - (ii) the cumulative attempt count across Phase 17 and every earlier run in scope,
    including runs that aborted, stopped at the checkpoint or hit the spend guard.
- **How a certification is quoted:** always with the cumulative count, pooled as a running
  total of attempts, not as a rate.
- **What falls outside:** a run whose success criterion is not a certified completion repair,
  and such a run may not claim one.

## Bounds

| | value | why |
|---|---|---|
| attempt cap | 60, **nominal** | the spend guard is a likely stop reason before 60 (next row) |
| spend guard | $150 at the conservative bound. No new study starts once spent + $11 headroom > $150, so ~$139 is the last start threshold and total spend can reach ~$149 | on stored stage costs, the guard stops a no-success run before 60 attempts in roughly 15–30% of runs at the central estimate, and 60–75% if the step rate is 0.27 (the figure depends on the assumed stage shares) |
| operator checkpoint | 12 | the user approves any continuation |
| circuit breaker | 5 consecutive infrastructure deaths | historical full-study death rate ~25%. The chance of a spurious trip within 60 attempts is 15.6% at 4-in-a-row and 4.1% at 5. None of the 10 historical deaths came from the channel the re-read fixes (6 lab-error/EvidenceDenied, 3 Mechanic provider errors, 1 StoreConflict), so the death rate is not expected to fall. A legitimate NO_CHANGE never counts |
| study timeout | 90 min | T15 took 10.4 min |
| expected cost to first success | ~$55 at the bound | ~25 attempts × ~$2.2. Token counts suggest the real bill is ~10× lower (unverified) |

Budget before this run: **$436.73 conservatively charged, $563.27 remaining** of the shared
$1,000. The true row sum is $0.28 lower; the higher figure is carried.

## Operator procedure (every step recorded under `artifacts/phase17-<date>/`)

1. **Confirm idle.** `/api/config/status` shows `active_campaign_id: null`, and the store
   (read-only) holds no QUEUED or RUNNING study.
2. **Stop the running backend and simulator.** The backend on :8000 has been up since 10:17
   and predates every Phase 16 edit; the runner would refuse it.
3. **Start the simulator:** `scripts/start-simulator.sh` (no reload, keep-alive 75), detached
   with `nohup` and its output going to `simulator.log`.
4. **Start the backend** without reload, detached (`nohup`) so that ending an agent session
   cannot kill it:
   - use the `os.environ.update` + `execv` recipe in `memory/context/runtime-and-evidence.md`;
   - apply **only the non-empty values** of `settings-phase17.json`, exactly as
     `expected_configuration.py` and the runner do;
   - never use `start-live-backend.sh` (its defaults are the Llama Actor with Aria on) or
     `start-backend.sh` (reload);
   - send output to `backend.log`.
5. **Check the backend:** `/api/health`, `/api/config/status` (live; actor V3.1; mechanic
   V4-Pro; no active campaign) and `/api/readiness`.
6. **Check ingestion:** `./.venv/bin/python scripts/experiments/check_ingestion_health.py`
   must exit 0.
7a. **Check the runner's own sha:** `shasum -a 256 scripts/experiments/run_full_loop.py` must
   equal the value in the pins table, and `docs/part2/PHASE17_EXPERIMENT.md` must be
   committed to the backup branch. The runner records its sha.
7. **Run with every pin:** `./.venv/bin/python scripts/experiments/run_full_loop.py --out artifacts/phase17-<date>
   --settings artifacts/phase16-2026-09-22/settings-phase17.json
   --expect-freeze artifacts/phase16-2026-09-22/gate-freeze-after.json
   --expect-freeze-sha256 96dc32a05d7e715c9752aa7837f1593c967efc02df975a332dea3e5f45faa20f
   --expect-configuration-hash c4169ee49deb7fb27ac44205d6e74b4f89912d1b43bf945636745b1872110418
   --stop-after 12 --execute-live --confirm-entity shreetbohara-quinstreet`, teed to `runner.log`.

   Before it starts, the runner refuses unless all of these hold:
   - the freeze file has the declared sha and contains the unchanged `assess_pairs`;
   - the code on disk equals the freeze;
   - every process on :8000 is a non-reload uvicorn started after the newest source file;
   - the models match;
   - `--confirm-entity` equals `WANDB_ENTITY` in the settings file and the settings project
     is `shreetbohara-quinstreet/Faultlab`.

   The runner cannot read the backend's entity directly. The backend itself refuses live work
   unless its confirmed entity equals its configured entity.

   During the run:

   | check | if it fails |
   |---|---|
   | backend process identity, before and after every attempt | abort |
   | each campaign's `configuration_hash` equals the declared hash | abort before its study starts |
   | the campaign appears in the reconciled store with Aria off | abort |
   | every study echoes v4, v2-task-outcome, `replay_of` null and the manifest hash, at start and after finishing | abort |
   | every verified evidence row for a study names the declared project | abort after that study |

   Outcomes are never lost:
   - A terminal outcome is saved the moment the poll sees it.
   - A study whose start reply was lost, but which the server did start, is adopted. The
     runner looks again once the backend is idle.
   - A row interrupted before its study id was saved is recovered on resume.

   Signals:
   - **Ctrl-C (SIGINT)** stops the running study.
   - **SIGTERM and SIGHUP** leave it running, to be recovered later. SIGHUP is ignored under
     `nohup`.
   - A killed session leaves `stop_reason: running`, which resume treats as an abort needing
     approval.

   Two limits:
   - **The evidence-project check** passes silently for a study with no verified evidence.
     A wrongly launched project whose reads all fail is then caught by the breaker, not after
     one study.
   - **Other completion studies:** while Phase 17 is open, nothing else may create completion
     studies on this store. Reconciliation treats any such study as untracked and refuses to
     resume.
8. **At the checkpoint:** `run_full_loop.py --out … --reconcile` must report 0
   discrepancies and 0 untracked studies. Then I report to the user.

## What each outcome would mean

- **Certified.** The loop, run fresh, produced a repair that passes a strict, pre-declared
  test and completes a sibling case at least two more times than the baseline. That is the
  project's first end-to-end result, reported with its denominator, S4 and the funnel.
- **Step candidates appear and qualify, but validation keeps dying** on untriggered faults or
  evidence. The bottleneck is batch fragility. The next phase would be about the Actor lapse
  behind 73 of 73 untriggered faults, never about loosening the gate.
- **Step candidates appear but do not qualify on v4.** The source gate or the Actor under v4
  is the constraint. Report which checks failed.
- **Checkpoint rule (a) fires.** Stop this design, and report it with the wording above. It
  is not a claim that the step rate fell.

## What must not happen

- No operator-initiated replay, re-validation or resumption of any Phase 17 study or
  candidate. A fresh study in which the Mechanic draws an identical policy again is part of
  the loop. It is counted and reported, never excluded.
- No edit under `backend/app`, and no edit to the runner or `gate_freeze.py`, while the run
  is live.
- No change to the success definition, the thresholds or the read-outs after data exists.
- Nothing is called ACCEPTED.
- The primary is never quoted without the funnel and S4.
- **Any stop other than the checkpoint (certified, attempt cap, spend guard, breaker or
  abort) ends the session.**
  - Continuing after an abort needs the user's approval and uses `--resume --after-abort`
    on the **same** `--out`, so spend, attempt numbers and the first-hit sequence carry over.
  - The runner refuses a fresh run in a second `phase17-*` folder.
  - Certified, attempt cap and spend guard are final.
- The cap is not raised after a failure.

## Review log

### Round 1 — five lenses, 2026-09-22, before any paid call

All five returned `RUN_WITH_CHANGES`: gate integrity, re-read safety, runner safety,
read-out and spend, and live configuration. Every blocking problem was attacked by an
independent skeptic, and all survived. What changed because of them:

**Mistakes of mine the review caught:**
- a runner test had been failing since I raised the breaker from 4 to 5, and my earlier
  "all tests pass" report had loaded the old version;
- the "after" freeze file cited in two documents did not exist;
- "all four failures were C6" was false: it is 3 of 4, with the 4th an untriggered trial;
- "16 of 17" should have been 17 of 17.

**Changes to what is claimed and measured:**
- Condition 3 raised from "gain ≥ 1" to "gain ≥ 2 on a single case", because the first
  version could certify a source-only policy by baseline noise ~10–20% of the time.
- `certified()` now also enforces the study identity (condition 1).
- `contains_step` now requires `service: notifications`, the Phase 9 predicate.
- The runner reports S1 and S2 without the terminating study.
- S2 split into a conditional and an unconditional figure.
- Checkpoint rule (a) reworded as a spend decision.
- Breaker odds, effective spend ceiling and S4 denominator corrected.
- Pooling rule added.

**Runner safety:**
- A terminal outcome could be lost if the post-idle re-read failed. It is now saved the
  moment it is seen, recovered on resume, and the outer handler catches everything.
- A study started server-side after a client-side start error is now adopted.
- `reconcile()` now flags silent gaps, non-terminal studies and anything run after the first
  certified study, and resume refuses unless it is clean.
- An abort can no longer be bypassed with a new folder.
- The stop is sent only to a campaign that is actually running.
- The manifest is written atomically, and SIGTERM and SIGHUP are handled.
- Consecutive poll failures are tolerated for 5 minutes before aborting.

**Live configuration:**
- The backend's configuration hash is now pinned to a declared value, cross-checked against
  Phase 15.
- The backend process is pinned per attempt.
- The campaign's store and Aria flag are checked.
- The evidence project is checked.
- Settings, runner and freeze-script hashes are in `declared`.

**Re-read hardening:**
- An alive-but-uninitialized worker is restarted.
- Unexpected errors are labelled `ERROR`.
- The health check counts each re-read episode exactly once.
- New tests cover TRANSPORT from a dead worker, a timed-out re-upload and an unexpected
  error.

### Round 2 — three lenses on the round-1 changes, 2026-09-22, before any paid call

Verdicts:
- runner v2: `RUN_WITH_CHANGES`;
- backend and pins: `SAFE_TO_RUN`. The freeze and the expected configuration hash were
  independently reproduced, and the Phase 15 cross-check confirmed;
- protocol consistency: `RUN_WITH_CHANGES`.

What changed:
- **Blocking, and caused by a round-1 fix.** Refusing any campaign without a charge bound also
  refused campaigns whose study never started (no ledger exists). One failed start would have
  ended Phase 17 for good. Fixed: the route's no-ledger body, with no study on the campaign,
  counts as $0. A real ledger with no bound still aborts.
- **Signals, caused by a round-1 fix.** SIGTERM/SIGHUP no longer stop the running study (it
  might be the first success). They leave it running for recovery, and SIGHUP respects
  `nohup`.
- **Approval after a hard kill.** A session killed hard now leaves `running`, and resume
  requires approval for anything but a clean checkpoint. Orphans from an interrupted start
  are recovered. A study created after a lost start reply is looked for again once idle.
- **Stopping only what is running.** The stop is sent only while the last attempt is actually
  unfinished.
- **Documents:**
  - declared how an abort after a finished study is read;
  - required same-policy reporting;
  - described the integrity pins accurately, and hard-coded them in the runner;
  - defined the pooling rule's scope;
  - corrected the chance levels (≈11% / ≈0.2–0.3%) and the spend-guard figures;
  - added the step candidates lost to infrastructure;
  - fixed S3/S4 in a read-out script before any data;
  - pinned the 17-assessment test by id, so a future result cannot turn it red.
- **A test mistake of mine found while fixing this:** my first version of the new runner
  tests hung. The fake backend only became idle when a study's status was read, and the
  adoption path never read it. The fake is now realistic, and every test caps the idle wait
  at 2 seconds so any such fault fails fast.
