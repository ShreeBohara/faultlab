# Phase 23 protocol — fixed-N full loop: 30 attempts, no stop at a success

**Status: declared before any paid call; reviewed in Phase 22 rounds 1–2 and frozen on 2026-09-24. Approval: artifacts/phase23-<run date>/review.json.**

Program: `docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md`, Phase 23. Runner:
`scripts/experiments/run_full_loop_fixed_n.py`, which imports the reviewed Phase 17 runner
`run_full_loop.py` unchanged. Built, reviewed and frozen in Phase 22 (`PHASE22_EXPERIMENT.md`).
§2 lists every place this document departs from the program or from Phase 17.

No money may be spent until:
1. Phase 22's freeze is taken and this document's pins are filled (`PHASE22_EXPERIMENT.md` §8
   steps F4–F8);
2. the phase is approved on its own and the review record exists (§9 step 0);
3. **heldout-2 is sealed and its seal committed (`PHASE22_EXPERIMENT.md` §8 step F9, §7.4 S5), or
   Phase 22's review judged v2 a weakening and cancelled Phase 24** (round 1). Phase 24 relies on
   the seed being made before Phase 23 produces any policy, so that no one can make the seed with
   the routed policy in view. The approver checks that the S2 and S5 commits on the backup branch
   precede this run's start. Those commit times come from the local clock on a local, unpushed
   branch, so they are **operator-attested** (round 2); the seed's sha256, which the operator sent
   the user in a message at S2, is the record outside the repository.

## 1. The question

On the fixed lab, with the byte-identical Mechanic brief, the v4 Actor context and the Phase 17
settings, **how often does a fresh full study certify a completion repair?**

Phase 17 answered a different question: whether it can happen at all. It stopped at its first
success (attempt 9 of 9), so its 1 of 9 is a first-hit event and not a rate. Phase 23 fixes the
number of attempts in advance and never stops at a success, so the count of certified attempts
has an honest interval.

It also produces the one policy that Phase 24 may check on heldout-2, chosen by a rule (§6).

## 2. Where this protocol departs from, or clarifies, the program or Phase 17

| # | program or Phase 17 | this protocol | why |
|---|---|---|---|
| 1 | Phase 17: stop at the first certified study; checkpoint after 12 attempts | **N = 30, fixed; a certified study never stops the run; no checkpoint** | the program's design. A continuation happens only after an early stop (§4.3) |
| 2 | Phase 17 pooling rule: a certification is quoted as a running total of attempts, not a rate. Program: "pooled (k+1)/39" | both: the cumulative count "*k*+1 certifications in *n*+9 attempts across Phases 17 and 23" **and**, beside it only, the pooled share with its Wilson interval and caveat | the program asked for the pooled figure, and Phase 17's rule still applies to every run in its scope. The pooled share is biased upward by Phase 17's stop at success, and is never quoted alone |
| 3 | program: "re-draws of dd62c857 counted but never re-checked" | a re-drawn `dd62c857…` is counted, and **never routed to heldout-2**. Inside its study it still goes through the source gate and validation, and pays for them | a study cannot skip a candidate without changing the loop; its held-out verdict is what is final |
| 4 | program: "the first **new** certified hash" | "new" = any policy hash without a held-out verdict. Only `dd62c857…` has one, so T15's `ec1acaf7…` would be routed if re-drawn and certified first | the only reading that needs no judgment at run time. Confirmed or changed at review (`PHASE22_EXPERIMENT.md` R8) |
| 5 | program: "validation acceptance on clean vs dirty batches" | reported, and **acceptance on a dirty batch is labelled zero by construction** | `assess_pairs` returns INCOMPLETE on any invalid trial (pitfall 72). It is not a finding |
| 6 | Phase 17: S1 and S2 reported with and without the terminating study | reported once | no study terminates the run, so there is no stop-at-success bias to bracket |
| 7 | Phase 17 `reconcile()`: a certified row whose post-check failed is a discrepancy | read as **not certified** (Phase 17's own declared rule, case (i)), and the post-checks that do not need the backend process are re-run when a row is recovered | Phase 17's reconcile made a resume after such an abort impossible, and left rows whose post-checks never ran marked `pending` for good |
| 8 | runbook: `check_clock_drift.py --worlds --since <date>` | run by the runner after each session with `--since` = the run's exact start time, `--require-worlds` | narrower than a date, so earlier episodes that day are not counted. The operator also runs it by hand (§9 step 8) |
| 9 | "pinned completion.md sha"; the runner pinned in its protocol | `completion.md` is pinned (`e3b9362f…`). **This document does not quote the runner's sha**: the runner pins this document's sha, and a file cannot contain a hash of itself through the other. The runner's sha is bound by the review record, which the runner reads (§9 step 0), and is recorded in `PHASE22_EXPERIMENT.md`'s pins table | a cycle otherwise |
| 10 | routing | a routing is **usable only when the run is final** (`fixed_n` or `spend_guard`) and the routed row's post-checks passed (`routable: true`). The Phase 24 runner requires the same (`PHASE22_EXPERIMENT.md` R3) | a run that stopped early is not the declared run |
| 11 | every attempt is in the denominator | declared exactly (round 1): an attempt number is taken by every row the runner appends, including a $0 **runner refusal** of the campaign (configuration hash, missing hash, store or Aria check) and a **stop while `POST /api/campaigns` was in flight** (labelled "interrupted before its campaign was recorded (no study)"). These rows are reported by reason beside the primary (§5.3) | a row is appended before its campaign is created, so any other rule would need judgment at run time. The funnel's `studies_started` gives the rate over attempts that ran a study |
| 12 | `run_full_loop.infrastructure_death` feeds the breaker and the funnel | a **runner-side** row (the refusals and the stop above) is not an infrastructure death: the breaker skips it (it neither counts nor resets the streak) and the funnel does not count it (round 1) | it is not a failure of the loop's infrastructure; Phase 17's function counted any row with an `error` |
| 13 | Phase 17's run-record handling | the run record is **claimed with an exclusive create** right after the re-run guard and before the slow ingestion check, and an abort's reason is **saved at once**, before the in-flight stop, the idle wait and recovery (round 1) | two launches could both pass the guard in the ingestion check's window; a second signal during the post-abort wait could leave `running` with no reason on disk |

## 3. What is fixed, and what changed since Phase 17

### 3.1 Unchanged from Phase 17

| | value |
|---|---|
| one attempt | one fresh campaign and one fresh, unmodified completion study, exactly as in Phase 17: 6 controls (one invalid control of each kind tolerated), up to 2 Mechanic proposals, a 3-pair source gate per distinct candidate, one 42-episode validation batch for a candidate that qualifies. All single-shot, through the unchanged `execute_slots` and `assess_pairs` |
| success: **CERTIFIED** | Phase 17's conditions 1–3, unchanged (`run_full_loop.certified`): a full, non-replay study on v4 with `v2-task-outcome` evidence and manifest `7ab9368e…`; decision and validation both `OBSERVED_IMPROVEMENT`; **and** L − B0 ≥ 2 completions on a validation case other than `notification-2` and `healthy`. A row whose post-finish checks fail (identity re-check, evidence project, backend process pin) is **not** certified |
| gate | `assess_pairs`, text sha256 `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2` |
| referee | `scorer_hash` `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` (`checks.py` never opened) |
| cases | completion manifest `7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483` (development) |
| Actor | `deepseek-ai/DeepSeek-V3.1`, context `faultlab-actor-context/v4-indexed-evidence`, **passed explicitly** (the backend default is still v1, pitfall 69) |
| Mechanic | `deepseek-ai/DeepSeek-V4-Pro-0813`, temperature 0; brief `backend/app/agents/prompts/completion.md`, sha256 `e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673`, the file Phase 17 ran on |
| evidence shown to the Mechanic | `faultlab-compact-evidence/v2-task-outcome` |
| settings | `artifacts/phase16-2026-09-22/settings-phase17.json`, sha256 `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d`. Per-call bounds: Actor $0.0209, Mechanic $0.04984; $400 per-campaign allocation |
| guards, HTTP helpers, store readers, read-out rules | imported from `run_full_loop.py`, sha256 `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342`, unedited |

### 3.2 Changed since Phase 17 (all declared in their own phases)

- **The code.** Phase 18 (the held-out check; `PairedEvaluator.run`'s optional
  `actor_context_protocol`, default unchanged), Phase 19 (per-campaign reads for the two
  dashboard endpoints; a 10 s lab connect budget; the drift checker) and Phase 22 (held-out v2;
  three optional request fields). **Every frozen function's text on the study path equals the
  Phase 16 freeze that Phase 17 ran on** (`PHASE22_EXPERIMENT.md` §4). The configuration hash
  has moved: `c4169ee4…` (Phase 17) → `1b6e5ed0…` (Phase 18) → `0a33aa51…` (Phase 19) → the
  Phase 22 value in the pins (computed at the freeze; round 1's draft `d235e428…` predates round
  1's edits and is stale).
- **The runner.** New; the main loop, `recover()` and the abort handling are copied from
  `run_full_loop.main` because they are nested inside it. Only the stop rule, the pins, the
  output prefix, the per-attempt funnel, the pending-post-check recovery and `reconcile()` differ,
  and, since Phase 22 review round 1, the labelling of a row interrupted during campaign create,
  the runner-side rows' exclusion from the death count, the early save of an abort's reason and
  the exclusive claim of the run record (§2 rows 11–13).
- **The runbook.** Phase 19's checks (simulator start-up flag, dashboard closed, drift check
  after), and the ingestion check run by the runner itself.
- **The provider.** Temperature 0 is not deterministic on it (Phase 21: 36% of repeat pairs
  byte-identical). The Mechanic's draws across attempts are correlated, but not copies.

## 4. Design

### 4.1 Attempts

- **N = 30 attempts, fixed in advance** (a constant in the runner, not a flag).
- Every attempt is in the denominator, including a campaign-create or study-start failure that
  ran no study, a $0 runner refusal of the campaign, and a stop while the campaign create was in
  flight (§2 rows 11 and 12). Rows that ran no study are listed by reason beside the primary.
- Attempt rows are numbered 1..*n* and only ever appended. A row left with no campaign by a stop
  (or a hard kill) is labelled when the runner aborts, or on resume; it is never recovered,
  because no study can start without a recorded campaign.

### 4.2 Stop rules (the only ones)

| stop | when | final? |
|---|---|---|
| `fixed_n` | 30 attempts recorded | **final** |
| `spend_guard` | no study starts once charged + $11 headroom > $150 | **final**; reported "Truncated at n=*j*" |
| `breaker` | 5 consecutive infrastructure failures | no: resumes only with the user's approval |
| `aborted` | Ctrl-C (stops the running study), SIGTERM or SIGHUP (leave it running for recovery), a failed pin or check, any other abort | no: resumes only with the user's approval |

**A certified study never stops the run.** There is no checkpoint.

### 4.3 Continuation after an early stop

- Only `--resume --after-abort`, on the **same** `--out`, with the user's approval. Spend,
  attempt numbers and the order of attempts carry over.
- Resume refuses if the declared parameters, pins, code, runner or settings differ from the run
  on record, if a row has no recorded outcome and its study is not terminal or readable, or if
  `reconcile()` finds any discrepancy or untracked study.
- `fixed_n` and `spend_guard` are final; they are never resumed or topped up.
- A second `phase23-*` folder is refused. The run record is created exclusively before the
  ingestion check, so a second launch in the same window is refused too (§2 row 13).

## 5. Declared read-outs

All are computed by the runner from the attempt rows (`summarize_fixed_n`) and saved in the
manifest's `summary`. None may be re-declared after data exists.

### 5.1 Primary

**k of n attempts certified, with a Wilson 95% interval.** Pre-fixed wording, none of which may
be reworded afterwards:
- `fixed_n`: "*k* of 30 attempts produced a certified completion repair (Wilson 95% [*lo*,
  *hi*])."
- `spend_guard`: "Truncated at n=*j* by the $150 spend guard: *k* of *j* attempts produced a
  certified completion repair (Wilson 95% [*lo*, *hi*])."
- `breaker`: "Stopped at n=*j* after 5 consecutive infrastructure failures: *k* of *j* attempts
  produced a certified completion repair (Wilson 95% [*lo*, *hi*]) up to that point. This is not
  a finding about the loop."
- `aborted`: "Stopped at n=*j* because *reason*: *k* of *j* attempts produced a certified
  completion repair (Wilson 95% [*lo*, *hi*]) up to that point."

The primary is **never quoted without** the funnel (§5.3), the untriggered-fault rate (§5.5),
the number of distinct certified policies (§5.4) and the cumulative count (§5.2).

### 5.2 Secondary: pooled with Phase 17

- **Cumulative count (Phase 17's pooling rule):** "*k*+1 certifications in *n*+9 attempts across
  Phases 17 and 23".
- **Pooled share, beside it only:** (*k*+1)/(*n*+9) with its Wilson interval, and this caveat
  every time: "Phase 17 stopped at its first success (attempt 9 of 9), so its share is biased
  upward."
- No test between Phase 17 and Phase 23 is declared.

### 5.3 The stage funnel (per attempt and summed)

| stage | definition |
|---|---|
| controls stops | studies that ended NO_CHANGE at `controls` |
| infrastructure deaths | `run_full_loop.infrastructure_death`, listed by `error_type` from the rows, **except runner-side rows** (§2 row 12) |
| attempts without a study | every row with no study, counted by its recorded reason (`attempts_without_study`), and the runner-side ones separately (`runner_side_no_study`) |
| **S1, step present** | first proposals whose policy contains `retry_original_request` with `service: notifications` at `after_notification_response` (the Phase 9 predicate), ÷ first proposals drawn. A refusal or an invalid first proposal is a draw without the step; "no proposal requested" is no draw. Reference, not adjudicating: Phase 17, 3 of 7 [16%, 75%] |
| **step fires** | step-containing candidates in which, in at least one source-gate trial, **the policy itself dispatched `send_confirmation`** (a `tool_dispatched` event with `caller: policy`), read from the `events` table (pitfall 50). Also counted: step-containing candidates whose step never fired (pitfall 77: a retry gated on PENDING never fires after a transient failure, which reads UNKNOWN), and validation trials in which it fired |
| **S2, source gate given the step** | (i) qualified ÷ step candidates whose source pairs were complete; (ii) qualified ÷ every step candidate tested. Reference: Phase 17, 2 of 4. Candidates without the step that qualify are counted separately |
| validation | reached; assessed; **clean** (an assessed batch with zero invalid trials) and **dirty**; accepted on clean ÷ clean. Accepted on dirty is **0 by construction** and is reported with that note |
| `OBSERVED_IMPROVEMENT` without a fresh gain | passed the unchanged gate but failed condition 3, so not certified. **Stated prominently** |
| certified | Phase 17's rule, post-checks passed |

### 5.4 Distinct hashes (pitfall 29)

Draws; distinct policies; distinct first proposals; distinct step policies; within-study
duplicates (slot 2 repeating slot 1); policies re-drawn across attempts, with their attempts;
certified attempts in order; **distinct certified policies**; and a block for `dd62c857…` with
its draws, its certified attempts and `routed: false`. Whether each certified hash existed in the
store before the run is a read-only query at report time.

### 5.5 The nuisance, quoted beside every validation result (S4)

The untriggered-fault rate per fault-bearing episode, **all stages, LAB_ERROR episodes
excluded** (exactly Phase 17's S4), with a Wilson interval. References: Phase 17, 1 of 153 =
0.65% [0.12%, 3.61%]; Phase 15 validation, 20 of 759 = 2.64%.

### 5.6 Also reported

- Evidence reads, re-reads and verified re-reads (the Phase 16 re-read).
- Cost at the conservative bound: total, per attempt, per certification. Token-priced cost is
  reported separately and labelled unverified.
- The drift check (§9 step 8): drifted and masked episodes, missing world files, exit status.
  Any drift is reported as a lab defect beside the result and **never earns a re-run**.

## 6. Routing (declared; the only link to Phase 24)

- **The rule:** the first attempt, by attempt order, whose row is certified and whose certified
  policy hash is not `dd62c857…`. Its policy hash is the **only** one Phase 24 may check.
- The manifest's `summary.routing` records the rule, the excluded hash, every certified attempt
  that carried it, and the chosen `policy_hash`, `attempt`, `study_id`, `campaign_id` and
  `post_checks`.
- **`routable` is true only when** the run ended at `fixed_n` or `spend_guard` **and** the chosen
  row's post-checks passed (`passed`, or `passed on recovery (backend process pin not
  re-checkable)`).
- **Phase 24 does not run** if no attempt routes, if the run is not final, or if Phase 22 cancelled
  Phase 24.
- Other certified policies are reported and **never** checked on heldout-2.
- **No development sweep, challenge, replay or probe of the routed policy** runs before its
  heldout-2 verdict. Nobody opens heldout-2.
- Because attempts are only appended, the first certified attempt cannot change after it
  happens. Routing is still read only from the final record.

## 7. Predictions, and what each count would show

**The per-attempt certification rate is unknown.** Phase 17's central prediction was ~0.04; on
v4 its step rate then came out higher (3 of 7). The program used 5–15%.

| per-attempt rate | P(*k* ≥ 1 in 30) | P(*k* ≥ 2) | expected *k* |
|---:|---:|---:|---:|
| 0.02 | 0.45 | 0.12 | 0.6 |
| 0.04 | 0.71 | 0.34 | 1.2 |
| 0.05 | 0.79 | 0.45 | 1.5 |
| 0.08 | 0.92 | 0.70 | 2.4 |
| 0.11 | 0.97 | 0.86 | 3.3 |
| 0.15 | 0.99 | 0.95 | 4.5 |

| *k* of 30 | Wilson 95% | pooled (*k*+1) of 39 | Wilson 95% |
|---:|---|---:|---|
| 0 | [0, 0.114] | 1 | [0.005, 0.132] |
| 1 | [0.006, 0.167] | 2 | [0.014, 0.169] |
| 2 | [0.018, 0.213] | 3 | [0.027, 0.203] |
| 3 | [0.035, 0.256] | 4 | [0.041, 0.236] |
| 5 | [0.073, 0.336] | 6 | [0.072, 0.297] |
| 8 | [0.142, 0.444] | 9 | [0.126, 0.383] |

**What this design can and cannot resolve.** At 30 attempts the interval is wide: 3 of 30 is
compatible with anything from 3.5% to 26%. It can separate "rare" (0 of 30 bounds the rate below
11.4%) from "common" (5 or more of 30 puts the lower bound above 7%). It cannot pin a rate
within a factor of two.

## 8. Bounds and cost

| | value | basis |
|---|---|---|
| attempts | 30, fixed | the program |
| spend guard | **$150** at the conservative bound. No study starts once charged + **$11** > $150, so the last start is at ≤ $139 and the total can reach about $149 | the worst case of one study is ~$10.23 (Phase 17) |
| expected cost | **$78–95** at the bound | Phase 17: $24.29 over 9 attempts = $2.70 per attempt; attempts that reached validation cost ~$6.08, others ~$1.73. $78 if 20% of attempts reach validation, $95 if a third do |
| truncation risk | the 30th attempt starts unless the first 29 average more than $4.79, which needs **over 70% of attempts to reach validation**. Every study at the $10.23 worst case would truncate at n=14 | the same stage costs |
| circuit breaker | 5 consecutive infrastructure failures. P(a spurious trip within 30 attempts): 0.04% at Phase 17's death rate (1 of 9), 1.9% at the historical ~25%, 8.8% at 35% | exact run-length probability |
| study timeout | 90 minutes | T15 took 10.4 minutes |
| duration | about 2–3 hours | Phase 17 ran 9 attempts in 40 minutes |
| budget before | $506.23 conservatively charged, **$493.77 remaining** of the shared $1,000. At the cap, ~$656 charged afterwards | |

Token-priced cost is about 10× lower than the bound; that is unverified.

## 9. Runbook

Record every step under `artifacts/phase23-<date>/` (the run's date). Every command runs from
the repository root.

0. **Preconditions, approval and the review record.**
   - Phase 22's freeze is taken, and this document's status line and pins were filled at
     `PHASE22_EXPERIMENT.md` §8 step F7, **before** its sha256 was pinned in the runner. Nothing
     may edit this document afterwards: the runner refuses a changed protocol.
   - `./.venv/bin/python scripts/experiments/run_full_loop_fixed_n.py --out artifacts/phase23-<date> --settings artifacts/phase16-2026-09-22/settings-phase17.json --expect-freeze artifacts/phase22-2026-09-24/gate-freeze-after.json --plan`
     shows every file pin `MATCH` and the configuration hash `pinned`. Save it as `dry-plan.txt`.
   - `shasum -a 256 scripts/experiments/run_full_loop_fixed_n.py docs/part2/PHASE23_EXPERIMENT.md`
     equals `PHASE22_EXPERIMENT.md`'s pins (`phase23-runner-sha256`, and the protocol row).
   - No `artifacts/phase23-*/full-loop-manifest.json` exists.
   - The approver approves the phase and writes `artifacts/phase23-<date>/review.json`, every sha
     as bare 64-character hex:

     ```json
     {"phase": 23, "status": "approved", "approved_by": "<name>",
      "protocol_sha256": "<sha256 of this document>",
      "runner_sha256": "<sha256 of run_full_loop_fixed_n.py>",
      "gate_freeze_file_sha256": "<the freeze sha from the pins>",
      "configuration_hash": "<the configuration hash from the pins>",
      "review_rounds": ["docs/part2/PHASE22_EXPERIMENT.md#review-log"], "approved_at": "<UTC time>"}
     ```

     The runner refuses a live run unless the record says `approved`, names the approver and
     repeats all four values.
1. **Ingestion health.** `./.venv/bin/python scripts/experiments/check_ingestion_health.py > artifacts/phase23-<date>/ingestion-health.txt`
   must exit 0. The runner runs it again at the start of every session and refuses if it fails
   (Phase 12 lost $8.15 without it). It stays a hard gate here (Phase 22 round 2): Phase 23's
   studies need Weave-verified evidence, unlike Phase 24's verdict. A refusal on `--resume` keeps the
   run record (tested). **Declared remedy:** the check reads the store's last 120 development
   ingestion rows, which move only when new development episodes are traced. If Phase 23 stops with
   a DEGRADED reading, a resume is refused until they move; what happens then is the user's decision
   (a separately declared and approved step that writes development episodes, or leaving Phase 23
   at its early stop, which never routes), never an edit of the runner, the check or its threshold.
2. **Simulator: keep it or restart it, by rule** (Phase 20 §9 step 2). Keep it only if its command
   line contains `--timeout-keep-alive 75`, its working directory is this checkout's `backend/`,
   and no file it imports (`backend/app/simulator`, `backend/app/config.py`,
   `backend/app/contracts`) changed after it started. Otherwise stop it and start it with
   `nohup scripts/start-simulator.sh > artifacts/phase23-<date>/simulator.log 2>&1 &`. Record the
   process either way.
3. **Dashboard closed.** Close every dashboard tab; stop the Vite server
   (`kill $(lsof -t -nP -iTCP:5173 -sTCP:LISTEN)`); `lsof -nP -iTCP:5173 -sTCP:LISTEN` prints
   nothing; the backend's request log stays still for 10 s. Then
   `./.venv/bin/python artifacts/phase19-2026-09-23/diagnosis/loop_latency.py 20 > artifacts/phase23-<date>/loop-latency.txt`
   must show **p99 < 100 ms**. That checks machine load only, and it measures the backend that step
   4 is about to replace, so it is **run again after step 4's restart** (round 2).
4. **Restart the backend deliberately on the frozen code.**
   - `curl -s http://127.0.0.1:8000/api/config/status` shows `active_campaign_id: null`, and this
     read-only query lists no `QUEUED` or `RUNNING` status (saved as `idle.txt`):
     `sqlite3 -readonly artifacts/lab.sqlite3 "SELECT kind, json_extract(payload,'$.status'), count(*) FROM records WHERE kind IN ('completion_studies','context_studies','heldout_checks') GROUP BY 1, 2"`.
   - Stop it (`kill -TERM $(lsof -t -nP -iTCP:8000 -sTCP:LISTEN)`), wait until nothing listens on
     :8000, then start the non-reload Phase 17 launcher:
     `nohup ./.venv/bin/python artifacts/phase17-2026-09-23/launch_backend.py >> artifacts/phase23-<date>/backend.log 2>&1 &`
     (sha256 `78911a29…`). **Never** `start-backend.sh` (reload) or `start-live-backend.sh`
     (Llama defaults, Aria on).
   - Check `/api/health`, `/api/config/status` (live; Actor V3.1; Mechanic V4-Pro; no active
     campaign) and `/api/readiness`.
   - Re-run the latency check on the new process (round 2):
     `./.venv/bin/python artifacts/phase19-2026-09-23/diagnosis/loop_latency.py 20 > artifacts/phase23-<date>/loop-latency-after-restart.txt`
     must also show p99 < 100 ms. Keep both outputs.
5. **Run**, lid open and on AC power:

   ```
   caffeinate -is ./.venv/bin/python scripts/experiments/run_full_loop_fixed_n.py \
     --out artifacts/phase23-<date> --settings artifacts/phase16-2026-09-22/settings-phase17.json \
     --expect-freeze artifacts/phase22-2026-09-24/gate-freeze-after.json \
     --review-record artifacts/phase23-<date>/review.json \
     --execute-live --confirm-entity shreetbohara-quinstreet 2>&1 \
     | tee -i artifacts/phase23-<date>/runner.log
   ```

   Before any study, the runner refuses unless: every pin is filled and every pinned file
   matches; the freeze carries the unchanged `assess_pairs`, `scorer_hash` and `completion.md`;
   the review record matches; the code on disk equals the freeze; the entity and project match
   the settings; every process on :8000 is a non-reload uvicorn started after the newest
   `backend/app` file; the backend is idle; ingestion is healthy.

   During the run, per attempt:

   | check | if it fails |
   |---|---|
   | backend process identity, before and after every attempt | abort |
   | the campaign's `configuration_hash` equals the pin | abort before its study starts ($0) |
   | the campaign is in the store with Aria off | abort |
   | the study echoes v4, `v2-task-outcome`, `replay_of` null and `7ab9368e…`, at start and after finishing | abort; the row is not certified |
   | every verified evidence row names the declared project | abort after that study; the row is not certified |

   Outcomes are never lost: a terminal outcome is saved the moment the poll sees it; a study whose
   start reply was lost but which the server did start is adopted; a row interrupted before its
   study id was saved is recovered on resume.
6. **During the run** nothing else touches the backend, the simulator or the store: no dashboard,
   no other study, no probe. Any other completion study created in the run window makes resume
   refuse.
7. **At the end**, the runner writes the summary and runs the drift check. If it stopped early,
   report the stop to the user and wait; continuing needs their approval (§4.3).
8. **Clock drift by hand:**
   `./.venv/bin/python scripts/experiments/check_clock_drift.py --store artifacts/lab.sqlite3 --since <started_at from the manifest> --worlds --require-worlds > artifacts/phase23-<date>/drift-check-manual.txt; echo "exit $?" >> artifacts/phase23-<date>/drift-check-manual.txt`.
   It must agree with the manifest's `clock_drift`. 0 = no drift, no masked fault, no missing
   world; 1 = a lab defect, reported beside the result; 2 = missing world files. Nothing here
   earns a re-run.
9. **Reconcile:** `./.venv/bin/python scripts/experiments/run_full_loop_fixed_n.py --out artifacts/phase23-<date> --reconcile`
   must report 0 discrepancies and 0 untracked full studies. Save the output.
10. **Write-up:** `PHASE23_RESULTS.md` with the §5 read-outs in their declared wording, the routing
    field, and every attempt's funnel row.

## 10. What each result would and would not mean

- ***k* ≥ 1 with a routable new policy.**
  - Would mean: on the fixed lab, the loop certifies a fresh completion repair at a rate
    compatible with the Wilson interval, and the funnel shows where the rest were lost. The routed
    policy goes to Phase 24.
  - Would not mean: ACCEPTED; held-out safety; an invariant repair; that the rate transfers to
    another Actor, context, manifest or brief.
- ***k* ≥ 1, but every certified hash is `dd62c857…`.** The loop re-finds Phase 17's policy. That
  is reported as reproduction of one policy, not of the loop's breadth. Phase 24 does not run.
- ***k* = 0 at `fixed_n`.** "0 of 30 (Wilson 95% upper bound 11.4%)": certification is rare under
  this setup. The funnel names the stage that loses it (no step, a step that never fires, the
  source gate, a dirty validation batch, a clean rejection, or condition 3). It is not "impossible".
- **Truncated at the spend guard.** The primary at *n* = *j* with its interval, never topped up.
  It would mean many attempts reached validation, which is upstream success; say so.
- **Breaker or abort, not resumed.** "Not a finding about the loop." No routing, so Phase 24 does
  not run.
- **Many certifications of one policy.** Report the distinct certified policies beside *k*. The
  Wilson interval treats attempts as independent; correlated re-draws make the effective sample
  smaller.
- **`OBSERVED_IMPROVEMENT` without a fresh gain.** It passed the unchanged gate and is not
  certified. Stated beside the primary.
- **Against Phase 17.** No comparison is declared. Phase 17's 1 of 9 is a first-hit event.

## 11. Limits

- **One configuration:** V3.1 Actor, v4 context, V4-Pro Mechanic at temperature 0, one brief, one
  development manifest. Development cases only.
- **Attempts are not independent draws.** The same brief and cases, and a provider whose
  temperature-0 outputs are correlated, produce re-draws. The distinct-hash accounting shows how
  much.
- **Validation is single-shot**, and its pass depends on every fault firing (S4, and the
  clean/dirty split).
- **Studies need Weave-verified evidence**, so the evidence channel still loses attempts
  (infrastructure deaths).
- **The drift checker detects; it does not prevent.** A drift is reported, not repaired.
- **The certification rule's condition 3 is realistically met only on `notification-3`**
  (Phase 17), a sibling of the source case.

## 12. What must not happen

- No operator-initiated replay, re-validation or resumption of any study, and no re-test of any
  candidate. A fresh study that re-draws a known policy is part of the loop: counted, never
  excluded.
- No edit under `backend/app`, to either runner, `gate_freeze.py`, `check_clock_drift.py`,
  `check_ingestion_health.py`, `completion.md`, the settings or this document after Phase 22's freeze
  (its §8 step F4), except the pin and status-line fills of its steps F7, F8 and F10 and their
  review-log lines (worded as in `PHASE22_EXPERIMENT.md` §8, round 2), while the run is live, or
  before Phase 24 has ended or been cancelled.
- No change to N, the cap, the headroom, the breaker, the certification rule, the routing rule or
  the read-outs once data exists. The cap is not raised after a truncation.
- No stop at a success; no top-up; no second `phase23-*` folder.
- Nothing is called ACCEPTED; no pointer moves; nothing is activated. `dd62c857…` is never routed.
- The primary is never quoted without the funnel, S4, the distinct certified policies and the
  cumulative count.
- No development sweep, challenge, replay or probe of the routed policy before its heldout-2
  verdict. Nobody opens heldout-2.

## Pins (filled at the Phase 22 freeze; `FILL-AT-FREEZE` until then)

| pin | value |
|---|---|
| reviewed code freeze | `artifacts/phase22-2026-09-24/gate-freeze-after.json`, sha256 `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1`. The code on disk must equal it |
| expected `configuration_hash` (Phase 17 settings on the Phase 22 code) | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba`. The first campaign must equal it, at $0 |
| settings file | `artifacts/phase16-2026-09-22/settings-phase17.json`, `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| Mechanic brief `completion.md` | `e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673` |
| base runner `run_full_loop.py` | `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342` |
| `gate_freeze.py` | `5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190` |
| `check_clock_drift.py` | `fa25ab9d38ed1287ff530751a4157eedffb8a0692e756bce0edef64133ae956a` |
| `check_ingestion_health.py` | `edde0190836898e2a301aadbb16906ded3ae20a5f51cd51bd4c4ee7266313c02` |
| `assess_pairs` text | `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2` |
| `scorer_hash` | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` |
| completion manifest | `7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483` |
| backend launcher | `artifacts/phase17-2026-09-23/launch_backend.py`, `78911a293492b803d6c688a6044cf6e578e2b1bd6b5ccd93c65029f42aca9827` |
| this document | its sha256 is pinned in the runner and repeated in the review record; it cannot appear here |
| the runner | its sha256 is in `PHASE22_EXPERIMENT.md`'s pins table and the review record; it cannot appear here |

```
gate-freeze-sha256: 8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1
configuration-hash: 2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba
```

## Review log

- **Phase 22 review round 1 (2026-09-23).** Logged in full in `PHASE22_EXPERIMENT.md` (Review log —
  round 1). Findings that touch this document or its runner, all applied: I7 (precondition 3: the
  seal before any spend), U3 (a row interrupted during campaign create), U6 (tests for every guard
  of the copied main loop), U8 (the denominator and the breaker: §2 rows 11–12, §4.1, §5.3), U9
  (an abort's reason saved at once), U10 (the exclusive claim), U11 (R6, the pin tests), N7 (the
  configuration-hash chain, §3.2). U1/N2 (R2, R3, R5) changed the Phase 24 runner, which now reads
  this runner's `summary.routing` and requires `run_final` and `routable`.
- **Phase 22 review round 2 (2026-09-23).** Logged in full in `PHASE22_EXPERIMENT.md` (Review log —
  round 2). Findings that touch this document or its runner, all applied (the runner's code is
  unchanged; its tests changed): C1 (the dry-plan test counted exactly six UNFILLED pins and would
  have failed once F8 filled them), A5a (a refused ingestion check on `--resume` keeps the run
  record, now tested), B6/C8 (precondition 3: the seal's commit times are operator-attested), B7/C5
  (§12's no-edit rule matches Phase 22 §8), C10 (§9 steps 3–4: the latency check re-run after the
  restart), and, noticed while applying A1/B2, the declared remedy for a stale DEGRADED ingestion
  reading (§9 step 1).
- **Approver decisions (2026-09-24, recorded in `PHASE22_EXPERIMENT.md`):**
  - v2 adopted, so Phase 24 runs and precondition 3 requires the heldout-2 seal;
  - R4, R8 and R9 confirmed ($87 cap);
  - N3 decided (a), a declared skip in `test_lapse_probe.py`.

