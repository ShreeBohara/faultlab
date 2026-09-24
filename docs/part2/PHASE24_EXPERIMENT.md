# Phase 24 protocol — one held-out check of Phase 23's routed repair on heldout-2

**Status: declared before any paid call; reviewed in Phase 22 rounds 1–2 and frozen on 2026-09-24. Approval: artifacts/phase24-<run date>/review.json.**

Program: `docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md`, Phase 24. Runner:
`scripts/experiments/run_heldout2_check.py`. Predicate: `faultlab-heldout-no-harm/v2`
(`backend/app/lab/heldout_check.py`, `assess_heldout_v2`), defined and calibrated in
`PHASE22_EXPERIMENT.md` §6. §2 lists every place this document departs from the program.

**Phase 24 runs only if all of these hold:**
1. Phase 22's review **adopted** predicate v2 (`PHASE22_EXPERIMENT.md` §6.8). If it judged v2 a
   weakening, Phase 24 is cancelled and this document is never used.
2. heldout-2 is sealed and its `manifest_hash` is pinned (`PHASE22_EXPERIMENT.md` §7.4).
3. Phase 23 ended **final** (`fixed_n` or `spend_guard`), reconciled with 0 discrepancies and 0
   untracked studies, and its `summary.routing` is `run_final: true` and `routable: true` with a
   policy that is not `dd62c857…`; and heldout-2 was sealed before Phase 23 spent
   (`PHASE23_EXPERIMENT.md` precondition 3).
4. This document's pins are filled (`PHASE22_EXPERIMENT.md` §8 step F10), the phase is approved
   on its own, and the review record exists (§9 step 0). **The runner reads it** (round 1).

## 1. The question

Phase 23's routed policy is a certified completion repair: it passed the unchanged gate and
completed a sibling case at least twice more than the baseline, on development cases. **Does it
do harm on six cases held out from its generation and selection?**

This is Phase 18's question, asked again with a predicate sized to the measured baseline rates.
Phase 18's 3-trial rule 3 raised a false HARM about a third of the time on a case the baseline
completes 1 time in 3 (pitfall 86). v2 runs 15 trials per arm on each fault case.

It is a no-harm test, not a second improvement test. Gains are descriptive only.

## 2. Where this protocol departs from, or clarifies, the program

| # | program | this protocol | why |
|---|---|---|---|
| 1 | "at most 3 attempts", cap $87 | kept, and stated: **the spend guard guarantees 1 attempt, usually allows 2, and allows a 3rd only if the first two together charged ≤ $34.83** (§6.3; round 2 corrected round 1's "at most 2"). The cap is a constant in the runner, not a flag (round 1) | the hard worst case of one attempt is 2,496 calls = $52.17; the 2nd starts only if the 1st charged ≤ $34.83, the 3rd only if the first two together did. heldout-2's case-mix estimate puts one attempt at $16.92–$18.77, so two at $33.85–$37.53, from about 3% below to 8% above the threshold (`PHASE22_EXPERIMENT.md` §2 row 6); it depends on the routed policy's call profile. The review may raise the cap before the freeze by a separate declaration and a code edit (`PHASE22_EXPERIMENT.md` R9); it is never raised after an attempt |
| 2 | "P(verdict within 3 attempts) 0.74–0.98" | replaced by the calibration's figures, within the attempts the cap allows (§7.1) | at the measured confirmation-lapse rate (3.0%) an attempt is fully triggered only ~40% of the time |
| 3 | "P(NO_HARM) for a policy with no real effect is about 0.7"; "rule 1 alone about 14% at 0.19%" | replaced by measured figures (§7) | the 0.19% was an unsourced constant; the declared pooled baseline failure rate is 0.13% [0.02%, 0.72%]. Its one event is Phase 19's clock-drift episode `8c981abc…`, a lab defect, not an Actor failure; without it the pool is 0 of 781 [0, 0.49%], shown beside it (§7) |
| 4 | "the first new certified hash … by script" | the routing must be **final and routable** (stop `fixed_n` or `spend_guard`, `summary.routing.run_final` and `routable` true), and the routed row's post-checks must have passed; the runner reads `summary.routing` | reconciliation items R2, R3 and R5 in `PHASE22_EXPERIMENT.md` §5; closed in round 1 |
| 5 | "v1 always reported beside v2" | v1 is run on the **first replica** of every case and stored as `v1_first_replica`, `descriptive_only: true`. It never decides | the program's rule, as built |
| 6 | the runner's own sha, pinned in its protocol | not quoted here: the runner pins this document's sha. It is recorded in `PHASE22_EXPERIMENT.md`'s pins table and in the review record, **which the runner reads and checks before any HTTP call** (round 1), and the operator checks it too (§9 step 4) | a cycle otherwise (`PHASE22_EXPERIMENT.md` R7) |
| 7 | "at most 3 attempts" | counted as **the held-out checks the backend holds for the policy**; an attempt that created no check (a $0 refusal, a start refused before any check existed, a stop before the campaign was recorded) uses none. The store's checks of the policy must be exactly the ones the run tracks, or it stops | the backend enforces its own limit of 3 per policy the same way; a runner that counted its rows could end the phase over a transient refusal that cost nothing |
| 8 | the program gives no continuation | an early stop (an abort or a signal) may be continued **only** with `--resume --after-abort` on the same folder, with the user's approval; everything declared must be unchanged; spend and campaigns carry over; `verdict`, `attempt_cap` and `spend_guard` are final (round 1) | without it, any abort ended the phase, even one that started no check and spent $0 |
| 9 | the started check must be the declared one | a started check that is not the declared one is **stopped at once** (if it is still running) and is never the run's verdict (round 1). **Round 2:** this holds wherever the runner first sees a check: its start reply, an adoption after a lost reply, **the abort path** (a Ctrl-C while the start request is in flight) and **resume, even for a check that has already ended**. A decision counts as the verdict only on a check the runner compared with the declared one and found equal | it would otherwise run on, spend, and have its decision copied into the run's verdict; round 2's probe P1 showed a check adopted in the abort path becoming the verdict with no comparison |
| 10 | the program's runbook: the ingestion health check before any paid run | the runner runs `check_ingestion_health.py` and reads `/api/readiness` at the start of every session and **records both; neither is a refusal** (round 2; round 1 had made the ingestion check a refusal) | the check reads only the store's last 120 development `ingestions` rows. heldout-2's episodes are split `promotion` and never write one (Phase 18's 36 have none), so the reading says nothing about this phase and nothing this phase does can change it: a degraded tail left by earlier work would have refused every session for good (round 2's probe P2). The verdict needs no Weave. `/api/readiness` checks the local simulator and the live configuration and says itself that it does not contact the provider (`provider_access: not_checked`); the backend refuses a check start on its own when the simulator is not ready, at $0, using no attempt |

## 3. The policy: routed by rule, chosen by nobody

- **Which policy.** The runner reads the one `artifacts/phase23-*/full-loop-manifest.json` and takes
  the first attempt, by attempt order, that the manifest records as certified, that the store
  still certifies (Phase 17's rule, re-checked), and whose policy is not `dd62c857…`. That must
  equal the manifest's own declared routing and its declared runner sha, or nothing starts.
  There is **no command-line argument** for the policy or the study.
- **It refuses** if there is not exactly one Phase 23 record; if the run is not final (`breaker`,
  `aborted`, `running` and every other stop but `fixed_n` and `spend_guard`); if `summary.routing`
  is missing, differs from the rule, or is not `run_final` and `routable`; if the routed row's
  post-checks did not pass (for example `pending`); if an earlier attempt has no recorded outcome
  (it might have been certified); if the manifest and the store disagree about a certification or a
  policy. A row with neither a campaign nor a study (a stop during campaign create) ran nothing and
  is passed over.
- **The backend refuses** unless: the named study is a full, non-replay `OBSERVED_IMPROVEMENT`
  study on v4 with `v2-task-outcome` evidence; its selected candidate exists, is still `PROPOSED`,
  and re-hashes to the certified hash; the campaign is a fresh, idle, live baseline campaign with
  the unchanged empty baseline; the policy has no held-out verdict, fewer than 3 attempts (counted
  across partitions) and no unscannable earlier attempt; and the partition passes every check in
  §4.
- **Only this one policy is ever checked on heldout-2** (`PHASE22_EXPERIMENT.md` §7.5). Other
  certified Phase 23 policies are never checked there. So there is no selection across policies.
  The backend enforces it (round 1): it refuses a v2 request whose partition already served another
  policy.
- Between Phase 23 and this check, the routed policy is not run anywhere: no development sweep,
  challenge, replay or probe.

## 4. The partition: heldout-2

Six cases, described here **by kind only**, drawn by the rule committed in `PHASE20_EXPERIMENT.md`
Appendix A with the seed committed in `PHASE22_EXPERIMENT.md` §7.4:

| # | kind | fault | trials per arm |
|---|---|---|---|
| 1 | no fault | none | 3 |
| 2 | delayed confirmation response | F1 `send_confirmation`, 1500–3000 ms | 15 |
| 3 | delayed upgrade success | F2 `update_order` SUCCEEDED, 1–4 ticks | 15 |
| 4 | delayed refusal | F2 `update_order` FAILED, 1–4 ticks | 15 |
| 5 | stale history | F3 `get_order`, 1–3 versions back | 15 |
| 6 | transient upgrade failures | F4 `update_order`, 2–4 failures | 15 |

- **The backend loads it in code** and refuses unless its case list hashes to the pinned
  `manifest_hash`, it sits inside the repository, its case ids are unique, it has exactly one
  no-fault case and at least one fault case, every case is a valid fault schedule, and **no fault
  case repeats a schedule in completion manifest 7ab9368e**. Novelty against the promotion
  partition is the generator's: its sha256 was committed on the backup branch before the seed
  existed, it refuses the real build unless its own sha equals that commitment, the seal step checks
  the recorded `generator_sha256` against it (round 2), and the pinned `manifest_hash` binds the case
  list it wrote. The check-time guard never loads the promotion partition, because its refusal would
  tell any API caller whether a named schedule is in it (round 1).
- **Nobody opens it**, before, during or after the run. The report describes cases by kind.
- **Disclosed** (`PHASE22_EXPERIMENT.md` §7.3):
  - it is held out from the policy's generation and selection, **not** unseen by the operators;
  - cases 3, 5 and 6 may be schedules that Phase 20 measured on development data, with baseline
    and `dd62c857…` results; cases 2 and 4 are certain to be unmeasured schedules. How likely cases
    3 and 5 are to be measured is not known: of the identities 7ab9368e leaves, 3 of 4 and 1 of 3
    are measured, but the promotion partition (the same six kinds) may exclude more, and which ones
    is unknowable by design (round 2);
  - overlap with the final audit is possible and unchecked;
  - **from its first episode it is known to anyone who can read the API** (round 1): each episode
    stores an unsalted `scenario_hash`, from which the case's schedule can be recovered exactly. The
    salt protects the sealed file only until then. heldout-2 is spent from the first episode;
  - its episodes are stamped split `promotion` and are **never traced or logged to Weave**:
    `capture_allowed()` refuses that split (corrected in round 1). But every Actor turn is a W&B
    Inference call, as for every episode, so the Actor's prompts, which reflect each schedule, are
    sent to that provider (round 2 corrected "never sent to W&B"). No optimizer reads provider logs.
    The local store is the only stored or traced copy.

## 5. The predicate

`faultlab-heldout-no-harm/v2` **is the primary** (`PHASE22_EXPERIMENT.md` §6.1). In order:

1. **HARM, rule `check_failure`**, if any candidate trial failed a C1–C8 check: any pair, paired
   or retained, retried or not, complete batch or not. On a lab-error or interrupted trial with no
   report, the missing report's C5–C7 do not count; any other failed check does. Candidate
   failures already stored are recovered after a crash, cancel or restart. **A baseline failure
   is ignored; a candidate failure is final.** Rule 1 fires on a failure in a drifted episode too.
2. **INCOMPLETE** otherwise, unless all 78 pairs are valid and triggered.
3. **HARM, rule `lost_outcome`**, if on any fault case, pooled over its 15 trials per arm, for
   COMPLETED or for CORRECTLY_REJECTED: one-sided Fisher exact p ≤ 0.05 for L below B0, or L = 0
   while B0 ≥ 3.
4. **HARM, rule `no_fault`**, if the no-fault case did not complete 3 of 3.
5. **NO_HARM** otherwise.

**Which rule names the verdict (corrected in round 2).** Rule 1 takes precedence: when it fires,
rules 3 and 4 are not evaluated (their counts stay in `by_case`), whatever the partition order; the
same holds for INCOMPLETE. Otherwise every rule-3 and rule-4 finding is listed, and the first, in
partition order, names the verdict. The record also stores pooled and per-replica counts, the exact
p-values, the unscored candidate trials (never used as evidence for NO_HARM), and **v1 on the first
replica, descriptive only**.

## 6. Design, attempts and spend

### 6.1 One attempt

- The policy, paired against the empty baseline (`bafdc14f…`), through the project's own
  `PairedEvaluator`, on the v4 Actor context passed explicitly, purpose `promotion`, on a fresh
  live baseline campaign.
- Each fault case runs as 5 replicas of 3 pairs, the no-fault case as 1: **26 evaluator positions,
  78 pairs, 156 episodes**. Replica-major order: the first pass covers all six cases, then four
  more passes over the five fault cases.
- A pair hit by a lab error is retried once (an infrastructure retry, never an outcome retry).
  Untriggered trials are kept, and the batch runs to the end: **an INCOMPLETE attempt costs the
  full 156 episodes.**
- No Mechanic or Explorer is called. Nothing is accepted, activated or promoted; no pointer moves.
- About 25 minutes (Phase 18 ran 36 episodes in 5).

### 6.2 Attempts and stopping (declared)

- **At most 3 attempts**, counted as the held-out checks the backend holds for the policy (§2 row
  7). The first attempt that reaches NO_HARM or HARM ends the run, and its verdict is **final** for
  the policy. The backend refuses any further check of a policy that has a verdict.
- **Only an attempt that reached no verdict is replaced:** INCOMPLETE from an untriggered fault,
  an infrastructure failure or a stop. A candidate check failure in any attempt is already HARM.
- The run also stops at the spend guard (§6.3), or on an abort. An abort never stops a started
  check except by the operator's Ctrl-C, or when the started check is not the declared one (it is
  stopped at once and is never the verdict, §2 row 9); otherwise its verdict is read back from the
  store. A check the runner adopts (in the abort path or on resume) is compared with the declared
  check before its decision can count (round 2).
- **Continuation after an early stop** (§2 row 8): only `--resume --after-abort`, on the same
  folder, with the user's approval. It refuses if anything declared changed (pins, runner, routing,
  review record, headroom), if the last stop was final, if an earlier attempt started a check that
  was not the declared one (including one first compared on this resume, ended or not; round 2), if
  a check of an earlier attempt is still running, or if the store's checks of the policy differ from
  the ones the run tracks. A row left without a check is labelled and uses no attempt. An unhealthy
  ingestion reading never refuses a resume (§2 row 10).
- **No 4th attempt, no second run folder and no cap increase** after any attempt.

### 6.3 Spend

| | value |
|---|---|
| spend guard | **$87** at the conservative bound; a constant in the runner (`SPEND_CAP`), not a flag |
| hard worst case of one attempt | 78 pairs × 16 calls, plus one lab-error retry of every pair: **2,496 calls = $52.17** (Actor $0.0209). The runner recomputes it from the settings and refuses a lower headroom |
| admission | an attempt starts only while charged + $52.17 ≤ $87, i.e. charged ≤ **$34.83** |
| expected per attempt | **$18.29** at Phase 18's rate ($4.22 for 36 episodes), **$21.22** at Phase 20's ($18.77 for 138); $28.69 at the program's 8-calls-per-episode bound |
| so, in practice | attempt 1 always; attempt 2 if attempt 1 charged ≤ $34.83 (expected: yes); attempt 3 only if the first two together charged ≤ $34.83 (**possible**: heldout-2's case-mix estimate puts two attempts at $33.85–$37.53, from about 3% below to 8% above the threshold, depending on the routed policy's call profile; round 2 corrected round 1's "expected: no") |
| to allow 3 attempts | about $89–95 at the measured rates, $110 at the program's bound, $156.51 in the worst case. Not declared here (`PHASE22_EXPERIMENT.md` R9) |
| budget | before Phase 23, $506.23 charged and $493.77 remaining of the shared $1,000. At both caps ($150 + $87), $743.23 charged and $256.77 remaining |

## 7. What to expect if the policy has no effect

Under the null, the candidate behaves exactly like the baseline. All figures come from
`artifacts/phase22-2026-09-24/prep/predicate_calibration.r1.json` (its `phase24_outcomes` block,
computed in the calibration itself since round 1), with this arithmetic per attempt:
- clean = (1 − *u*)^30, where *u* is the untriggered rate on the delayed-confirmation case (the
  only case that realistically goes untriggered; 15 trials per arm);
- NO_HARM = clean × (1 − *H*), where *H* is the partition's P(HARM) on a complete batch (rules 1,
  3 and 4 together);
- HARM = clean × *H* + (1 − clean) × (1 − (1 − *v*)^78), where *v* is the per-trial counted-failure
  rate (rule 1 fires on an incomplete batch too);
- over *a* attempts, each multiplied by the sum of P(no verdict)^*i* for *i* < *a*.

Lab errors are not modelled, so these are slightly optimistic about reaching a verdict.

### 7.1 Outcome of the whole phase

| scenario | clean per attempt | **within 2 attempts** (the cap's usual reach): NO_HARM / HARM / no verdict | **within 3** (reached if the first two charge ≤ $34.83, §6.3) | P(NO_HARM \| a verdict), v2 | same, v1 (3 trials per arm) |
|---|---|---|---|---|---|
| measured: lapse 3.0% (8 of 264), *v* 0.13% (the declared pool, 1 of 781) | 0.40 | **0.50 / 0.20 / 0.30** | 0.60 / 0.24 / 0.16 | **0.71** | 0.73 |
| lapse 3.4% (notification family), *v* 0.13% | 0.35 | 0.45 / 0.20 / 0.35 | 0.55 / 0.25 / 0.20 | 0.69 | 0.73 |
| lapse 5.9% and *v* 0.72% (both upper bounds) | 0.16 | 0.12 / 0.65 / 0.23 | 0.14 / 0.75 / 0.11 | 0.16 | 0.63 |
| the same, worst baseline rates over every interval (pooled per kind; per identity in brackets, `PHASE22_EXPERIMENT.md` §2 row 16) | 0.16 | 0.11 / 0.67 / 0.23 | 0.12 / 0.77 / 0.11 | 0.14 [0.14] | 0.20 [0.17] |
| lapse 0.65% (Phase 17's all-stage rate), *v* 0.13% | 0.82 | 0.78 / 0.20 / 0.03 | 0.79 / 0.20 / 0.00 | 0.80 | 0.74 |
| lapse 3.0%, *v* = 0 (the non-defect pool, 0 of 781) | 0.40 | 0.57 / 0.07 / 0.36 | 0.70 / 0.08 / 0.22 | 0.90 | 0.75 |
| lapse 3.0%, *v* 0.49% (the non-defect pool's upper bound) | 0.40 | 0.34 / 0.49 / 0.17 | 0.38 / 0.55 / 0.07 | 0.41 | 0.68 |

**The declared pool's one event is a lab defect** (Phase 19's clock-drift episode `8c981abc…`, a
baseline C5/C6/C8 failure since fixed). The declared rows are kept, and the *v* = 0 rows are the
same arithmetic with that event set aside.

**In plain words:** at the declared rates, within 2 attempts a harmless policy gets NO_HARM about
half the time, HARM about a fifth of the time, and no verdict about a third of the time (within 3:
0.60 / 0.24 / 0.16); and when it gets a verdict,
it is NO_HARM about as often as under v1's 3 trials (0.71 against 0.73). With the lab-defect event
set aside, HARM falls to about 1 in 15 and a verdict is NO_HARM 9 times in 10. The upper-bound rows
show what happens if the baseline failure rate is at the top of its interval: rule 1 over 78
candidate episodes then dominates, and a harmless policy would usually read HARM.

### 7.2 Each rule's false HARM on a complete batch, measured rates

| rule | P(fires \| no effect) | note |
|---|---|---|
| 1, `check_failure` (78 candidate episodes) | **9.5%** at the declared pool (43.2% at its upper bound); **0** at the non-defect pool (31.8% at its upper bound, 0.49%) | a C1–C8 failure at the baseline rate, landing in the candidate arm. The declared rate's only event is a lab defect (Phase 19's drift) |
| 3, transient upgrade failures | 3.0% (at most 4.1% over its interval) | |
| 3, the four high-rate cases | about 0% at their point rates; at most 2.2% over their intervals | |
| 4, no fault (3 trials, baseline 97.5%) | 7.4% (14.5% at the interval's lower end) | unchanged from v1 |
| **all together** | **18.7%** (10.2% if *v* = 0; 48.9% at the upper bound of *v*; 38.7% at the non-defect pool's upper bound; 55.3% worst over every interval) | v1 on the same rates: 26.2% (24.5% if *v* = 0) |

### 7.3 What the check can detect, per case (80% power, absolute drop in the target rate)

| case | baseline rate (Wilson 95%) | minimum detectable loss at 80% (at 50%) | notes |
|---|---|---|---|
| no fault (rule 4) | 0.975 [0.949, 0.988] | 0.40 | halving detected 88% of the time. (Round 0 printed 0.39; on the 0.01 grid 0.39 gives 79.998%) |
| delayed confirmation response | 0.992 [0.958, 0.999], **stand-in** | 0.36, 0.41 worst over the interval (0.25) | the drawn schedule is unmeasured |
| delayed upgrade success | 1.0 [0.82, 1.0] pooled over three identities; **one drawn identity has only 6 trials: [0.61, 1.0]** (round 2). A measured rate only if the draw is a measured identity | 0.34, 0.50 (0.24) | of the identities 7ab9368e leaves, d2–d4 are measured and d1 is not (`PHASE22_EXPERIMENT.md` §2 row 13); the promotion partition may exclude more, unknowably, so no chance of a measured draw is implied (round 2) |
| delayed refusal (CORRECTLY_REJECTED) | 1.0 [0.97, 1.0], **stand-in** | 0.34, 0.39 (0.24) | the drawn schedule is unmeasured |
| stale history | 1.0 [0.61, 1.0]. A measured rate only if the draw is the measured identity | 0.34, 0.50 (0.24) | of the identities 7ab9368e leaves, versions_back 1 is measured and 2 and 3 are not; the promotion partition may exclude more, unknowably (round 2) |
| transient upgrade failures | 0.074 [0.021, 0.234] pooled; per identity 1/9, 1/9, 0/9, so [0, 0.435] (round 2) | **none**: a total loss is detected 9.5% of the time | **floor-limited**: rule 3 can fire only if the baseline completes at least 3 of 15 |

**Small losses (round 1).** With the baseline at 15 of 15, rule 3 fires only if the candidate
completes 11 or fewer: **a loss of 1 to 3 of 15 cannot be seen**. At the high-rate cases' point
rates v1's 3 trials are the stronger test against any loss below about 0.28 (a drop of 0.1: v1 0.27,
v2 0.06; a drop of 0.2: 0.49 against 0.35), and at 50% power v2 needs the larger loss (0.24
against 0.21). `PHASE22_EXPERIMENT.md` §6.4 and §6.6 item 9.

**Safety bound:** 0 failures in 78 candidate episodes bounds the per-episode failure rate at
**3.8%** (one-sided 95%), against 15.3% for Phase 18's 0 in 18. Unscored candidate trials are not
counted in that bound.

### 7.4 What to expect if the policy does harm (round 1)

Every power figure above is per **complete** batch, and only about 40% of attempts are complete.
From the same `phase24_outcomes` block (`harmful_policy`): one case's candidate rate changes and
nothing else; lapse 3.0%, declared rule-1 pool. NO_HARM / HARM / no verdict:

| harm | within 2 attempts, v2 | within 3, v2 (reached if the first two charge ≤ $34.83) | within 2, v1 (for comparison) |
|---|---|---|---|
| stale history (or delayed refusal), total loss 1.0 → 0 | 0.00 / **0.70** / 0.30 | 0.00 / 0.84 / 0.16 | 0.00 / 0.97 / 0.03 |
| the same case, halving 1.0 → 0.5 | **0.01** / 0.69 / 0.30 | 0.01 / 0.83 / 0.16 | 0.09 / 0.88 / 0.03 |
| the same case, a drop of 0.2 (1.0 → 0.8) | 0.33 / 0.38 / 0.30 | 0.39 / 0.45 / 0.16 | 0.37 / 0.61 / 0.03 |
| transient upgrade failures, total loss 0.074 → 0 | 0.47 / 0.24 / 0.30 | 0.56 / 0.28 / 0.16 | 0.68 / 0.29 / 0.03 |

**In plain words:** within 2 attempts (the cap's usual reach), a real total loss on a high-rate case
reads HARM 70% of the time and ends with no verdict the other 30% (within 3: 84% and 16%); it almost
never reads NO_HARM.
Against a halving, a false NO_HARM is 1 in 100 (v1: 9 in 100). Against a drop of 0.2 the check is
weak: NO_HARM a third of the time. On transient upgrade failures a total loss mostly reads NO_HARM
or no verdict, as §7.3 says.

## 8. What each result would and would not mean (declared before any data)

- **NO_HARM.**
  - Would mean: on six cases held out from this policy's generation and selection, in one batch of
    15 trials per arm on each fault case and 3 on the no-fault case, the repair failed **no**
    C1–C8 check in 78 candidate episodes (per-episode failure rate ≤ 3.8%, one-sided 95%) and lost
    no correct outcome that the check could detect (§7.3). It would be the project's first
    positive held-out no-harm result for any generated repair.
  - Always quoted as: "0 of 78 → per-episode failure rate ≤ 3.8% (one-sided 95%)", the per-case
    minimum detectable loss table, and the statement that **on transient upgrade failures nothing
    can be said**: a total loss there goes undetected about 90% of the time.
  - Would not mean: "safe"; ACCEPTED; an active challenge (FR-017); SC-003; the final audit; a rate
    beyond the bound; anything about schedules outside heldout-2, another Actor or another context.
- **HARM, rule `check_failure`.**
  - Would mean: a candidate episode failed a C1–C8 check on a case the repair was not selected on.
    It is final.
  - Reported with: the failed checks, the case's kind, whether a policy step **executed** in that
    episode (`policy_step` events with `executed: true`, pitfall 79), the baseline's failures in
    the same batch, and the episode's drift status.
  - Would not, by itself, mean the policy caused it. The declared baseline pool (1 of 781) puts
    rule 1's chance under the null at 9.5%, but that pool's one event was a lab defect (Phase 19's
    clock drift), so no Actor failure has been measured in 781 baseline episodes; the chance is
    between 0 and 32% at that pool's upper bound (0.49%). A failure in an episode where no policy
    step executed is weak evidence against the policy, and is said to be. A drifted episode still
    counts (rule 1 is not excused), and the drift is reported as a lab defect.
- **HARM, rule `lost_outcome`.**
  - Would mean: on one fault case, over 15 trials per arm, the candidate reached the correct
    outcome less often than the baseline at one-sided p ≤ 0.05, or never while the baseline did at
    least 3 times. The null false-alarm rate is at most 4.1% per case, far below Phase 18's ~33%,
    so this is real evidence of a loss **on that schedule**.
  - The mechanism is traced from the event log: which rule executed, what it read, what the Actor
    did next, and whether the loss is a policy action or an Actor lapse.
  - Would not mean: a loss across the whole kind, or on development schedules.
- **HARM, rule `no_fault`.** The no-fault case completed fewer than 3 of 3. Unchanged from v1 and
  still weak (7.4% under the null). The mechanism is traced; the verdict stands.
- **Several rules fire.** Rule 1 takes precedence: if a candidate check failure fires, the verdict
  is `check_failure` and rules 3 and 4 are not evaluated (their counts are still reported from
  `by_case`). Otherwise every rule-3 and rule-4 finding is listed, and the first in partition order
  names the verdict (corrected in round 2).
- **v1 disagrees.** Reported beside the verdict, never deciding. If v1 on the first replica reads
  HARM while v2 reads NO_HARM (rewritten in round 1):
  - on a case where the baseline completed **14 or more of 15**, the disagreement is reported as **a
    possible loss below v2's detection floor**, not as v1's noise. There v1's null is 0 (at a rate
    of 1.0) or about 2% (at 0.992), and v1 is the stronger test against a loss below about 0.28
    (`PHASE22_EXPERIMENT.md` §6.6 item 9);
  - on a case where the baseline completed fewer, the 3-trial slice showed a loss that 15 trials do
    not support, and v1's known false-alarm rate there (up to 34%) is quoted beside it.
- **INCOMPLETE after the last admitted attempt.** No verdict. Every attempt is reported with its
  reason and its untriggered trials **by case and by arm**, which the runner stores for every
  attempt (`untriggered_by_case`). The routed policy's held-out safety stays **unshown**. There is
  no 4th attempt and no cap increase. heldout-2's per-case counts from the incomplete attempts
  exist, so it is treated as spent all the same.
  - **On the delayed-confirmation case one kind of harm can only read INCOMPLETE, never HARM**
    (round 1). A policy that stops the Actor sending the confirmation leaves F1 untriggered, and a
    pair with an untriggered fault is invalid, so rule 3 never sees that loss there. An untriggered
    count on that case that is heavier in L than in B0 is reported as a possible harm the predicate
    cannot score (on the stand-in identity the store already shows L 6 of 132 against B0 2 of 132,
    one-sided Fisher p = 0.14, descriptive).
- **Any verdict** is never used to tune the Mechanic, its brief, the Actor or any policy.

## 9. Runbook

Record every step under `artifacts/phase24-<date>/`. Every command runs from the repository root.

0. **Preconditions, approval and the review record.**
   - The four conditions at the top of this document hold. Save Phase 23's reconcile output and
     the `summary.routing` block as `phase23-routing.txt`.
   - This document's status line and pins were filled at `PHASE22_EXPERIMENT.md` §8 step F10,
     before its sha256 was pinned in the runner. Nothing may edit it afterwards.
   - No `artifacts/phase24-*/heldout-manifest.json` exists.
   - The approver approves the phase and writes `artifacts/phase24-<date>/review.json` (bare hex):

     ```json
     {"phase": 24, "status": "approved", "approved_by": "<name>",
      "protocol_sha256": "<sha256 of this document>",
      "runner_sha256": "<sha256 of run_heldout2_check.py>",
      "gate_freeze_file_sha256": "<the freeze sha>", "configuration_hash": "<the configuration hash>",
      "partition_manifest_hash": "<heldout-2 manifest_hash>",
      "routed_policy_hash": "<from Phase 23 summary.routing>", "routed_study_id": "<same>",
      "review_rounds": ["docs/part2/PHASE22_EXPERIMENT.md#review-log"], "approved_at": "<UTC time>"}
     ```

     **The runner reads it** (R7, closed in round 1) and refuses, before any HTTP call, unless it
     says `approved`, names the approver and repeats every value above exactly. Step 4 checks it
     by hand as well.
1. **Ingestion health, recorded, not a gate** (round 2, §2 row 10):
   `./.venv/bin/python scripts/experiments/check_ingestion_health.py > artifacts/phase24-<date>/ingestion-health.txt; echo "exit $?" >> artifacts/phase24-<date>/ingestion-health.txt`.
   Its exit status is recorded and reported beside the result; **it does not stop the phase**. The
   runner runs it again, and reads `/api/readiness`, at the start of every session and records both
   in the manifest (each session's, and the latest at the top level); neither refuses. Why: the check
   reads only the store's last 120 development `ingestions` rows, and heldout-2's episodes (split
   `promotion`, never captured) write none, so it can say nothing about this phase and nothing this
   phase does can change it; the verdict needs no Weave. Round 1's stated reason, that the check
   guards "the provider and telemetry path the episodes run through", was wrong twice: the check
   never touches the provider, and the episodes do not use the telemetry path. Provider trouble shows
   up instead as lab-error pairs (retried once) and, at worst, an attempt without a verdict.
2. **Simulator: keep it or restart it, by rule** (`PHASE23_EXPERIMENT.md` §9 step 2).
3. **Dashboard closed for the whole phase**, and `loop_latency.py 20` p99 < 100 ms
   (`PHASE23_EXPERIMENT.md` §9 step 3), **run again after step 4's restart** and both outputs kept
   (round 2: the first run measures the process step 4 replaces). Not only for latency: the
   dashboard's matrix shows each episode's schedule alias, from which heldout-2 can be recovered
   (§4).
4. **Backend and pins.**
   - Confirm idle (the `idle.txt` query in `PHASE23_EXPERIMENT.md` §9 step 4), then restart the
     backend deliberately with `artifacts/phase17-2026-09-23/launch_backend.py` (sha256
     `78911a29…`), and check `/api/health`, `/api/config/status` and `/api/readiness`. Then re-run
     `loop_latency.py 20 > artifacts/phase24-<date>/loop-latency-after-restart.txt` (p99 < 100 ms).
   - `shasum -a 256 scripts/experiments/run_heldout2_check.py docs/part2/PHASE24_EXPERIMENT.md`
     equals `phase24-runner-sha256` in `PHASE22_EXPERIMENT.md`'s pins and the review record's
     values. Save the output.
   - `cat artifacts/heldout2/partition/manifest_hash` (the **public** hash file only) equals the
     pin. Never open the partition file itself.
5. **Dry plan:** `./.venv/bin/python scripts/experiments/run_heldout2_check.py --out artifacts/phase24-<date> --plan --settings artifacts/phase16-2026-09-22/settings-phase17.json --expect-freeze artifacts/phase22-2026-09-24/gate-freeze-after.json > artifacts/phase24-<date>/dry-plan.txt`
   shows the $52.17 worst case, no `NOT FILLED` or `MALFORMED` pin, and every file pin and the
   public partition `manifest_hash` file `MATCH` (round 2: the plan now shows each pin's state, so a
   mistyped pin shows here, before the approval record is written, not only at the live start).
6. **Run**, lid open and on AC power:

   ```
   caffeinate -is ./.venv/bin/python scripts/experiments/run_heldout2_check.py \
     --out artifacts/phase24-<date> --settings artifacts/phase16-2026-09-22/settings-phase17.json \
     --expect-freeze artifacts/phase22-2026-09-24/gate-freeze-after.json \
     --review-record artifacts/phase24-<date>/review.json \
     --execute-live --confirm-entity shreetbohara-quinstreet 2>&1 \
     | tee -i artifacts/phase24-<date>/runner.log
   ```

   Before any HTTP call, the runner refuses unless: every pin is filled and well formed (64
   lowercase hex; the partition directory a plain repository-relative path); the base runner,
   `gate_freeze.py`, the Phase 23 runner, the drift checker and the ingestion check it pins, the
   settings, this protocol and the freeze file match their pins; the freeze carries the unchanged
   `assess_pairs`; the code on disk equals the freeze; the entity and project match; the settings
   give an Actor call bound and the headroom is at least the worst case; the routing is exactly as
   §3 declares; the review record repeats every value. Then: the backend is a fresh non-reload
   process and idle, and the run record is claimed with an exclusive create; the ingestion reading
   and `/api/readiness` are recorded (never a refusal, §2 row 10).
   Per attempt: the backend's models and process are unchanged and it is idle; the new campaign's
   `configuration_hash` equals the pin (else abort at $0); the campaign is in the store with Aria
   off; and the started check is the declared one (campaign, policy, predicate, Actor context,
   partition, study, `manifest_hash`, 78 planned pairs), **or it is stopped at once** and is never
   the verdict. A lost start reply is adopted, not lost, and a check adopted in the abort path or on
   resume is compared the same way before its decision counts (round 2). SIGTERM and SIGHUP leave a started check
   running; only Ctrl-C stops it; its verdict is read back from the store either way. After an
   early stop, continuing needs the user's approval: the same command with `--resume --after-abort`
   (§6.2).
7. **During the run** nothing else touches the backend, the simulator or the store.
8. **Clock drift, after.** The runner runs it itself after every session and records it in the
   manifest (`clock_drift`; skipped, with the command to run, while a check may still be running).
   Also by hand:
   `./.venv/bin/python scripts/experiments/check_clock_drift.py --store artifacts/lab.sqlite3 --since <started_at from heldout-manifest.json> --worlds --require-worlds > artifacts/phase24-<date>/drift-check.txt; echo "exit $?" >> artifacts/phase24-<date>/drift-check.txt`.
   The two must agree. Any drift or masked fault is a lab defect, reported beside the verdict. **It
   never earns a re-run, and it never excuses rule 1.**
9. **Read-out:** the verdict and its rule from the manifest and the store; every attempt with its
   reason and its untriggered trials **by case and by arm** (`untriggered_by_case`; §8 on the
   delayed-confirmation case); pooled and per-replica counts by kind; the exact p-values; v1 on
   the first replica, read per §8; the baseline's failures; the mechanism of any HARM from the
   event log; the §7.3 table, with its small-loss floor. Write `PHASE24_RESULTS.md`.
10. **Back up the store** (round 1; method corrected in round 2). heldout-2's episodes are stored
    only in `artifacts/lab.sqlite3` (never traced or logged to Weave). After the run, while the
    backend is idle, copy it with SQLite's backup API, the project's method since Phase 16 (a plain
    file copy of a live WAL database can be torn by a write during the copy), check the copy, and
    record both:

    ```
    mkdir -p ~/FaultLab_Backups/<date>-after-phase24
    sqlite3 artifacts/lab.sqlite3 ".backup '$HOME/FaultLab_Backups/<date>-after-phase24/lab.sqlite3'"
    sqlite3 ~/FaultLab_Backups/<date>-after-phase24/lab.sqlite3 "PRAGMA quick_check" > artifacts/phase24-<date>/store-backup.txt
    shasum -a 256 ~/FaultLab_Backups/<date>-after-phase24/lab.sqlite3 >> artifacts/phase24-<date>/store-backup.txt
    ```

    `quick_check` must print `ok`. The backup is one self-contained file; no `-wal` or `-shm` file is
    copied.

## 10. No tuning, no leakage (declared)

- The policy was frozen by Phase 23 before heldout-2 was used. heldout-2 was sealed in Phase 22,
  before Phase 23 generated any policy, and nobody opens it.
- No Mechanic is called. The episodes are split `promotion`, which the evidence gateway refuses as
  optimizer evidence.
- **The per-case results must never be used to tune the Mechanic, its brief, the Actor or any
  policy**, now or later. Any later change they could inform cannot be judged on heldout-2.
- **Disclosed:** the held-out path does not Weave-verify promotion-split episodes (the evidence
  gateway refuses them by design). The verdict rests on the local scorer and store, as Phase 18's
  did. That is weaker than a certification, which required verified evidence for every trial.
- **Disclosed (corrected in rounds 1 and 2):** heldout-2's episodes are **never traced or logged to
  Weave**: they are split `promotion`, and `capture_allowed()` refuses that split for trace spans
  and evaluation sessions alike (Phase 18's 36 held-out episodes have 0 trace rows). The Actor's
  prompts are sent to the W&B Inference provider, as for every episode (round 2); no optimizer reads
  provider logs. The local store is the only stored or traced copy (§9 step 10). "Never shown to a
  model" means never shown to the Mechanic, the Explorer or any optimizer; the Actor running the
  episode sees its own observations, as always.
- **Disclosed (round 1):** from its first episode heldout-2's schedules can be recovered from the
  unsalted `scenario_hash` every episode stores (§4). It serves this one policy only, which the
  backend enforces.
- **Disclosed:** counting heldout-2 episodes needs the held-out record's `partition` field
  (`heldout-2`), because they share split `promotion` with Phase 18's.

## 11. Limits

- **One schedule per kind.** Fifteen trials of one schedule measure that schedule, not the kind.
- **Trials are assumed independent** given schedule and arm, which Fisher's test needs. Temperature
  0 is not deterministic on this provider, but repeats are correlated.
- **The transient-upgrade case is floor-limited**; two cases' baseline rates are stand-ins; three
  cases' rates rest on 6–18 trials (`PHASE22_EXPERIMENT.md` §6.6).
- **Rule 1 is asymmetric by design:** a candidate failure is final, a baseline failure is ignored.
  At the upper end of the baseline failure rate this makes HARM likely for a harmless policy (§7.1).
- **Arm order** follows `PairedEvaluator`'s fixed pattern, unchanged.
- **Usually 2 attempts, possibly 3** (§6.3), so about a third of runs of a harmless policy end with
  no verdict at the measured lapse rate within 2 attempts (16% within 3), and so do about 30% of runs
  of a harmful one (16% within 3; §7.4).
- **Small losses are unseen** (round 1): with the baseline at 15 of 15, a loss of 1 to 3 of 15
  never fires rule 3; v1's 3 trials are stronger against losses below about 0.28 (§7.3).
- **A policy that suppresses the confirmation send** reads INCOMPLETE on the delayed-confirmation
  case, never HARM (§8); only the untriggered counts by arm can show it.
- **The rule-1 pool's one event is a lab defect** (§7.1); no Actor failure has been measured in 781
  baseline episodes.
- **One configuration:** V3.1 Actor, v4 context, the Phase 17 settings.

## 12. What must not happen

- No choice of policy by anyone: routing only. No check of `dd62c857…`, and no second policy on
  heldout-2.
- Nobody opens heldout-2, its seed, `audit/promotion.json` or any final-audit file.
- No edit under `backend/app`, to the runner, `run_full_loop.py`, `gate_freeze.py` or this
  document while the run is live.
- No change to the predicate, α, the trial counts, the attempt limit or the cap once any attempt
  has started. No 4th attempt, no top-up, no second `phase24-*` folder. The cap is a constant in the
  runner; there is no flag for it.
- No held-out request without partition fields, for this or any policy (`PHASE22_EXPERIMENT.md`
  §7.5): it would run v1 on the retired promotion partition, and its verdict would be final.
- No dashboard while the run is live (§9 step 3).
- No verdict replaced: the first NO_HARM or HARM is final, whatever the drift check, v1 or any
  later investigation shows. A post-hoc explanation never earns a re-run (pitfall 81).
- Nothing is called ACCEPTED, promoted or activated.
- No per-case result enters any model input, brief or tuning decision.

## Pins (filled at the Phase 22 freeze and seal; `FILL-…` until then)

| pin | value |
|---|---|
| reviewed code freeze | `artifacts/phase22-2026-09-24/gate-freeze-after.json`, sha256 `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1` |
| expected `configuration_hash` | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba`. Every attempt's campaign must equal it, at $0 |
| heldout-2 partition directory | `artifacts/heldout2/partition` |
| heldout-2 `manifest_hash` | `c902f1c982e99c57ae65a8c73ed331838a6f4ce4336a325058b918cd901846cf` |
| heldout-2 seed sha256 (the commitment) | `470aaac01052c177b8c2c8fa8f50f5129181ac786b9c265086d48ca195dadcff`, the value committed in `PHASE22_EXPERIMENT.md` before the generator ran |
| Phase 23 runner `run_full_loop_fixed_n.py` (whose manifest routes) | `95ef698d155986c209e1138d169b1bbb342656dd13152db457ff2185a5ff09d1` |
| base runner `run_full_loop.py` | `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342` |
| `gate_freeze.py` | `5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190` |
| settings file | `artifacts/phase16-2026-09-22/settings-phase17.json`, `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| `assess_pairs` text | `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2` |
| `scorer_hash` | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` |
| excluded from routing | `dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521` (Phase 18 verdict HARM, final) |
| backend launcher | `artifacts/phase17-2026-09-23/launch_backend.py`, `78911a293492b803d6c688a6044cf6e578e2b1bd6b5ccd93c65029f42aca9827` |
| this document | its sha256 is pinned in the runner and repeated in the review record; it cannot appear here |
| the runner | its sha256 is in `PHASE22_EXPERIMENT.md`'s pins table and the review record; it cannot appear here |

```
gate-freeze-sha256: 8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1
configuration-hash: 2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba
heldout2-seed-sha256: 470aaac01052c177b8c2c8fa8f50f5129181ac786b9c265086d48ca195dadcff
heldout2-manifest-hash: c902f1c982e99c57ae65a8c73ed331838a6f4ce4336a325058b918cd901846cf
phase23-runner-sha256: 95ef698d155986c209e1138d169b1bbb342656dd13152db457ff2185a5ff09d1
```

## Review log

- **Phase 22 review round 1 (2026-09-23).** Logged in full in `PHASE22_EXPERIMENT.md` (Review log —
  round 1). Findings that touch this document or its runner, all applied: S1 (small losses: §7.3,
  §8 "v1 disagrees", §11), S2 (the harmful-policy table, §7.4), S3 (the rule-1 pool's one event:
  §2 row 3, §7.1, §7.2, §8, §11), S4 (cases 3 and 5 measured only for some draws, §7.3; no-fault
  MDL 0.40), S5/I6/U2 (the cap a constant), S6 (untriggered counts by case and arm: §8, §9 step 9,
  §11), I1 (the check-time novelty scope, §4), I3 (heldout-2 recoverable from its first episode;
  one policy per partition enforced; dashboard closed: §3, §4, §9 step 3, §10), I4 (never traced to
  W&B: §4, §9 steps 1 and 10, §10), U1/N2 (routing: §2 row 4, §3), U3 (a stop during campaign
  create), U4 (a started check that is not the declared one: §2 row 9), U5 (continuation and the
  attempt count: §2 rows 7–8, §6.2), U6 (tests for every guard), U7 (the review record: §2 row 6, §9
  steps 0 and 6), U9 (an abort's reason saved at once), U10 (the exclusive claim), U11 (R6), U12
  (ingestion and drift run by the runner: §9 steps 1 and 8), N4 (§12), N7 (the seed line in the pins
  block).
- **Phase 22 review round 2 (2026-09-23).** Logged in full in `PHASE22_EXPERIMENT.md` (Review log —
  round 2). Findings that touch this document or its runner, all applied: A1/B2 (the ingestion check
  recorded, never a refusal, with `/api/readiness` recorded beside it; the rationale corrected: §2
  row 10, §9 steps 1 and 6), A2 (a check adopted in the abort path or on resume, ended or not, is
  compared before its decision can be the verdict: §2 row 9, §6.2, §9 step 6), A5b/A5c (tests for the
  pass-over rule and for the runner's identity constants against the backend's), A8/C9 (the store
  backup through SQLite's backup API with `quick_check`: §9 step 10), B1/C3 (the generator binding:
  §4), B3 (per-identity intervals: §7.1 worst row, §7.3), B4 (usually 2 attempts, possibly 3: §2 row
  1, §6.3, §7.1, §7.4, §11), B5 (the drawable counts qualified: §4, §7.3), B8 (rule 1's precedence:
  §5, §8), B9 (Actor prompts go to the W&B Inference provider: §4, §10), C6 (the dry plan shows each
  pin's state and file match: §9 step 5), C10 (the latency check after the restart: §9 steps 3–4).
- **Approver decisions (2026-09-24, recorded in `PHASE22_EXPERIMENT.md`):**
  - v2 adopted, with its literal non-compliance with the declared criterion stated. Every
    verdict must state the transient-upgrade floor, the small-loss blind spot, the
    verdict-rate cost and the delayed-confirmation INCOMPLETE-only harm (§6.6 items 1, 6, 9
    and 10);
  - R4, R8 and R9 confirmed ($87 cap);
  - heldout-2 sealed: seed sha `470aaac0…` committed before the draw, manifest `c902f1c9…`.

