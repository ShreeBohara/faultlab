> Produced 2026-09-23 by a planning workflow: 4 survey lenses, 4 adversarial verifiers and
> 1 synthesizer, all read-only at $0. The scripts and outputs it cites are in
> `artifacts/program-2026-09-23/`; paths below that say `scratchpad/program/` refer to that
> copy. Each phase is still declared, reviewed and approved on its own before it spends.

**FaultLab experiment program, Phases 20 to 27 (2026-09-23 to the event, about 2026-10-12)**

Every dollar figure is a conservative per-call bound. Token-priced cost is about 10 times lower, but that is unverified. Wherever I say "estimate", I did not measure it.

## 0. Two facts that change how the proposals should be read

1. **Runtime 2 removed the Actor's "no report" failure.** That was the only failure an incumbent ever repeated 3 of 3.
   - PHASE2_RESULTS.md, experiment C1: with the strict final-report schema, the 5-tick delayed upgrade went from 10 of 10 violations to 10 of 10 SAFE_UNRESOLVED. The 4-tick case completed 9 of 10.
   - All 19 reproduced counterexamples, and the v1 dose-response figures the held-out reviewers quoted (223 of 231 failures), come from before runtime 2.
   - So the held-out lens's fear, that F2 no-report failures would dominate partitions and challenges, rests on old data. The ACCEPTED lens's premise is refuted by the same data.
2. **Phase 18 would have been HARM even without the clock drift.** Two reviewers verified this independently.
   - With the drifted episode set to a clean completion, rule 3 still fires on stale history: candidate 2 vs baseline 3. PHASE18_RESULTS shows the policy acted 0 of 3 times on that case, so the loss was an Actor lapse.
   - Rule 3 also fires on transient upgrade failures (0 vs 1).
   - CLAUDE.md:180 and PHASE19_RESULTS.md:150 ("the one verdict the defect decided") therefore overstate. The defect decided which rule fired first, not the verdict.
   - The deeper problem is that the n=3 predicate reacts to noise. My computation (scratchpad/program/design_tradeoff.out): per case, it raises a false HARM 33-34% of the time when the baseline completion rate is between 0.33 and 0.5, and 8% at 0.97.

## 1. Dropped or redesigned

**Held-out lens (HO)**
- **HO-1's rule for sending dd62c857 to heldout-2: dropped.** Phase 18's verdict is final (heldout_check.py:134), and a second draw for that policy would be repeat-until-lucky. HO-1 survives, merged into Phase 20, with these changes:
  - F4 count 1 dropped. The broker's automatic re-send absorbs one failure, so that setting tells us nothing.
  - Two pooled primaries tested with Holm, instead of 7 per-setting tests (per-setting power at the Holm level was only about 0.48).
- **HO-2's dd62c857 arm: dropped (finality).**
  - The v2 rule "one-sided Fisher at n=9" is dropped: it cannot fire while the baseline completes 3 of 9 or fewer, so it is weaker than v1 exactly where dd62c857 lost.
  - Stress cases are dropped (contradictory rules; the spec text they cite is about the final audit).
  - The generator is redesigned: occurrence fixed at 1, and a declared novelty rule, because the development space already contains every F2-success delay.
- **HO-3: kept, merged with P4.**
  - It becomes a fixed-N run with no stop at the first success.
  - The runner changes the reviewer listed are required: new pins, output prefix, re-run guard, stop rule, and `reconcile()`.
- **HO-4: downgraded to an optional challenge-style probe.** It does not close any spec step. Its main refutation (the challenge dies on a shared no-report failure) no longer holds after runtime 2.
- **HO-5 (Llama): dropped.**
  - The "4 of 6" figure includes B1 ReferenceActor episodes.
  - v4 has never run with Llama.
  - The strict reading is dominated by noise.
  - Swapping the live backend's Actor model mid-program is risky.

**ACCEPTED lens (ACC)**
- **ACC-0, ACC-3, ACC-4 and ACC-5: dropped.** Under runtime 2 there is no incumbent failure that reproduces 3 of 3:
  - post-contract F2 d≥5 baseline results: 0 of 16 C5;
  - the highest v4 baseline family rate is 16 of 240;
  - the two post-contract learning campaigns found no source.
  - So P(ACCEPTED) is about 0, and the final audit cannot legitimately be spent.
- **ACC-1: shrunk to a baseline source-existence check** inside Phase 20. Its "our citation fix removed the failure" headline would be a false attribution; runtime 2 did it.
- **ACC-2: its target is obsolete.** The duplicates come from copying `candidate_history`, not from temperature 0. It is retargeted into the Mechanic slot-2 probe (Phase 26c).

**Yield lens**
- **yield-1:** Stage B dropped (its read-outs ride on the next paid run). Stage A kept at $0, redesigned as a 2x2 so the positive control becomes a read-out in its own right.
- **yield-2:** redesigned, per its reviewer:
  - the primary becomes turn-4 recovery, with a placebo arm;
  - a report-wording check (R4) is added;
  - v5 is built inside the probe script, not in progress.py;
  - the stop rule on reproduction is removed;
  - the rationale uses development data only (Phase 18 is used as a motive nowhere).
- **yield-3:** as written, guards G2 and G5 block adoption about 50% and 99% of the time under the null, and G1 cannot fail. Guards will be recalibrated before spending.
- **yield-4:** Steps 1 and 2 dropped (dormant channel, survivor-biased population, and removing the circuit breaker is risky). Replaced by a $0 fake-worker test, passive counting, and a pre-declared trigger.
- **yield-5:** restricted to v4-era inputs. The corrective turn and the T2 "lab-assisted" arm are kept out of any adoption path.
- **yield-6:** redesigned. An analytic per-case model becomes the primary; the development resample cannot see low-completion-rate cases.

**Robustness lens**
- **P1:** the time-drift framing is dropped (a slicing artefact: validation-only p=0.23). The determinism measurement is kept inside Phase 21.
- **P3:** the day-block drift test is dropped. It merges with yield-3, safety becomes co-primary, and readings are based on intervals.
- **P2:** merged into Phase 20 with failure counts {2,3,4}. It is labelled a "development probe", not the spec's active challenge.
- **P5:** kept at $0, with 40 full-suite runs plus a loaded-CPU arm, run only when no paid run is active.

## 2. Merges

| Merged phase | Sources |
|---|---|
| Phase 20 | HO-1 + P2 + ACC-1-lite + the F2 measurement HO-4 needs + yield-6's analytic calibration |
| Phase 21 | yield-2 + P1 |
| Phase 22 | HO-2 (partition and predicate) + the $0 pieces of yield-1 Stage A, P5 and yield-4 |
| Phases 23 + 24 | HO-3 + P4 |
| Phase 25 | yield-3 + P3 + yield-1 Stage B |
| Phase 26 | HO-4 (a); ACC-1's reference-policy idea (b); yield-5 + ACC-2 (c) |

## 3. The program

| Phase | Dates | Cap | Depends on |
|---|---|---|---|
| 20: Upgrade-side dev probe of dd62c857 + source-existence check (+ $0 foundations) | Sep 23-26 | $28 | none |
| 21: Actor replay probe (lapse fix v5, temperature-0 stability) | Sep 24-26 (parallel) | $25 | none |
| 22: Build, review twice, freeze once, seal heldout-2; $0 validity track | Sep 27-Oct 1 | $0 | 20, 21 |
| 23: Fixed-N full loop, 30 attempts, v4, no stop at success | Oct 2 | $150 | 22 |
| 24: Held-out check of the first new certified repair on heldout-2 | Oct 3-4 | $87 | 23 (k≥1) |
| 25: dd62c857 replays on fixed lab, with v4 vs v5 lapse A/B if Phase 21 passed | Oct 5-6 | $110 (or $60) | 21, 22 |
| 26: Small probes: (a) Explorer challenge of dd62c857, (b) second completion gap, (c) Mechanic slot 2 | Oct 7-8 | $23 | 20, 22 |
| 27: Event write-up and demo (not the only remaining work, the last) | Oct 8-11 | $0 | all |

Runbook for every paid run (one at a time):
1. Run `check_ingestion_health.py`.
2. Start the simulator with `start-simulator.sh`.
3. Close the dashboard and check that `loop_latency` p99 is under 100 ms.
4. Pin the configuration hash.
5. Afterwards, run `check_clock_drift.py --worlds --since`.

Any drift is reported as a lab defect and never earns a re-run.

### Phase 20: upgrade-side development probe of dd62c857, plus a source-existence check

**Question.** On the development fault kinds dd62c857 was never selected on, does it lose completions or add check failures compared with the empty baseline? Under v4 plus runtime 2, does any schedule give a 3 of 3 incumbent failure?

**$0 steps before spending:**
- (a) Draft the Phase 18 counterfactual correction for CLAUDE.md, PHASE19_RESULTS, START_CLAUDE and next-phase.
- (b) Commit the heldout-2 construction rule and the sha256 of a fresh os.urandom seed (details in Phase 22). The rule has no data-dependent branches.
  - *Amended 2026-09-23 (Phase 20 review round 1):* the rule is committed in Phase 20, in `PHASE20_EXPERIMENT.md` Appendix A, with the draw spaces this program left open now fixed (the F2 FAILED delay range, the F1 unit, range and uniform draw, the novelty scope and the re-draw procedure). Only the seed, its generation and its sha256, moves to Phase 22, and it is committed there before any draw. The commitment takes effect when the reviewed protocol's sha256 is recorded in `artifacts/phase20-2026-09-23/review.json`, before Phase 20 spends.
- (c) Count, per fault kind, the distinct occurrence-1 schedule identities in development episodes and in completion manifest 7ab9368e. Counts only.
- (d) Build the analytic null-calibration model: per-case false-HARM for rules 1, 3 and 4 as a function of the baseline completion rate and violation rate, plus the rule-3 dominance table (see Phase 22).
- (e) Note from the store: the notification-2 family has 247 v4 baseline episodes with 16 violations, so it cannot supply a 3 of 3 source. It needs no paid trials.

**Design.**
- Paired B0 (bafdc14f) vs L (dd62c857), v4 explicit, fresh development campaign so evidence stays isolated.
- Run through PairedEvaluator's fixed 3 trials, with replicas listed. Seeds are metadata, so results are reported as "schedule x pairs", never as distinct cases.
- Blocks:
  - A: F4 update_order, failure counts 2, 3 and 4, 9 pairs each (27 pairs).
  - B: F2 update_order SUCCEEDED, delays 2, 3 and 4, 6 pairs each (18).
  - C: F1 update_order 1500 ms, 6 pairs; F3 versions_back 1 (history-v1), 6 pairs (12).
  - D: F2 SUCCEEDED at d16, at d20, and at d20 plus F1 update_order 1500 ms, 3 pairs each (9).
  - Healthy: 3 pairs.
- Total: 69 pairs, 138 episodes.
- Target outcome per setting is declared from the case-definition code before spending. The d16 and d20 settings target SAFE_UNRESOLVED.

**Declared read-outs:**
- P-1 (loss): Block A pooled, L below B0 on target outcomes, one-sided Mantel-Haenszel stratified by count, Holm over 2. If B0 completes 4 of 27 or fewer, the result is declared floor-limited ("cannot detect a loss").
- P-2 (gain): Block B pooled, L above B0. The expected result is null, because B0 at d≤4 completes about 9 of 10 under runtime 2.
- Safety: every C1-C8 failure per arm and setting, each drift-checked. An L failure where B0 is clean is reported as a "development counterexample". It is never written REJECTED.
- Source check: Block D B0 fails the same invariant 3 of 3 (yes or no).
- Descriptive:
  - per-setting outcome tables;
  - Actor calls;
  - no-report count;
  - `policy_step` events with `executed: true`, by hook;
  - the baseline's update_order re-send rate;
  - untriggered counts.
- Calibration output: B0 completion rate per kind. This is B0 only; L results never feed the predicate.

**Power (estimate).** About 0.9 if B0 completes about 1/3 of Block A and L never does. Near 0 if B0 completes 10% or less. The measured B0 rate says which regime we are in.

**Decision rules:**
- Source check null (expected): record "ACCEPTED is unreachable in the trusted configuration. The runtime-2 report protocol removed the only reproducible incumbent failure." T065, T097 and T102 are then recorded as blocked by the absence of a source, not by tooling.
- Source check finds a 3 of 3 failure: record it. A separately declared ACCEPTED scoping phase could be funded from the reserve (v4 pin, promotion-v2 partition, K=1, end after the first promotion decision). This is not planned.
- P-1 significant: a characterized development limitation of dd62c857 (it trades completions for caution on transient upgrade failures), with the mechanism taken from the event log. It changes nothing in the Mechanic brief.
- P-1 null with B0 at 1/3 or more: Phase 18's 0 vs 1 is bounded as probable noise.
- Floor: "cannot tell", and heldout-2's transient-upgrade kind becomes a low-rate case, which is stated in its verdict.

**Code.**
- `scripts/experiments/run_dev_probe.py`, run in-process with the backend stopped, as in repeatability.py. No `backend/app` file changes, so the Phase 19 freeze and configuration hash 0a33aa51 stay valid.
- Reuse the existing Purpose literal `'challenge'`, and write its own plan and result records, not ChallengeResult records.
- Tests, `PHASE20_EXPERIMENT.md`, and one adversarial review of the protocol plus the runner.

**Cost.** 138 × 8 × $0.0209 = $23.07, plus 10% for retries. Cap $28. **Days:** 3.5.

### Phase 21: Actor replay probe (non-scoring)

**Question.** After one UNKNOWN reply, does telling the Actor "no confirmation requested yet" (v5) make it send the confirmation? Does it do so without changing other decisions or report wording? And how often does the Actor at temperature 0 give a different answer to byte-identical input?

**Design.**
- Rebuild prompts from stored events plus `private_episode_inputs.intent`, development split only.
- Verify `messages_hash` and `request_hash` for each prompt. Set `response_format` per context with `response_format_for(stored response_contract)`, because 18 of the 28 report turns are strict-schema turns.
- Count and report any prompt that fails its hash check.
- Arms:
  - C: the exact v4 prompt re-sent;
  - T: v5, built in the probe script only;
  - P: a placebo field with the same shape and no meaning.
- A $0 pre-check: rebuilding all v4 turns under v5 changes only the in-window turns and 0 terminal-rejection turns.
- Populations:
  - turn-4 prompts from the 65 v4 lapse episodes (store baseline: 0 of 296 later sends);
  - turn-3 prompts from the same 65 lapse episodes;
  - 100 non-lapse turn-3 prompts;
  - 65 in-window report turns;
  - for determinism, 28 historical-PENDING and 28 matched historical-UNKNOWN report-turn contexts, repeated 5 times under C.

**Declared read-outs:**
- Primary: on turn 4, T's send rate is at least 0.8, and T minus P is at least 0.5 with Fisher p < 0.01. This is stated as a contrast.
- R3: T and P match C's action class on at least 95% of non-lapse prompts, with 0 reports.
- R4: no change in notification wording (such as NOT_STARTED) on report turns without a contract-checked reason.
- Turn-3 flips are descriptive only, shown beside P's flip rate.
- Determinism:
  - the share of repeats that are byte-identical;
  - the per-call rate r at which the notification word flips (Wilson interval);
  - PENDING probability for historical-PENDING vs historical-UNKNOWN contexts.
  - It never outputs "time drift".

**Decision.** The primary, R3 and R4 must all pass before v5 enters Phase 22's change set and Phase 25's A/B. Otherwise record "the lapse is not fixed by stating the missing state" and keep the untriggered channel fatal.

**Code.** `scripts/experiments/lapse_probe.py`, dry by default, requiring `--execute-live` and `--confirm-entity`. Outputs are saved as files and never enter a study.

**Cost.** About 1,050 requests × $0.0209, cap $25. **Days:** 3, in parallel with Phase 20.

**What results mean.**
- Pass: every untriggered fault in 4,791 episodes traces to one decision, and one windowed field flips it on the exact prompts that failed.
- Fail: the lapse is stochastic or not state-driven, which is still a sharp result.

### Phase 22: build, review twice, freeze once, seal heldout-2 ($0)

**Change set** (one freeze, with `assess_pairs` 783e8e58 and `scorer` 19de811c re-verified at function level):

1. **heldout_check.py:**
   - a partition directory plus a pinned manifest_hash, replacing `load_cases('promotion')`;
   - record `'partition'`;
   - keep the per-policy finality guard;
   - add `assess_heldout_v2`.
2. **Predicate v2.** Rules 1 and 4 are unchanged. Rule 3 is chosen by a criterion I declare now:
   - v2 must match or beat v1's power on each harm scenario at the Phase-20-measured baseline rates;
   - it must have a lower false-HARM rate under the null;
   - the verdict states the minimum detectable loss per case.

   Leading candidate: 15 trials per arm per fault case, HARM if one-sided Fisher p ≤ 0.05 OR (L = 0 and B0 ≥ 3). My computation (design_tradeoff2.out):

   | Baseline rate | Harm scenario | v2 null false alarm | v2 power | v1 null false alarm | v1 power |
   |---|---|---|---|---|---|
   | 0.33 | full loss | 0.020 | 0.92 | 0.33 | 0.70 |
   | 0.2 | full loss | 0.030 | 0.60 | 0.29 | 0.49 |
   | 0.97 | drop to 0.6 | about 0.001 | about 0.77 | 0.08 | 0.75 |
   | 0.1 | full loss | 0.039 | 0.18 | 0.20 | 0.27 |

   - At a baseline rate of 0.1 the candidate is weaker than v1 (0.18 vs 0.27). No design with 15 trials or fewer fixes that, and it is stated.
   - v1 is computed on the first replica and always reported beside v2.
   - If review judges v2 a weakening, Phase 24 is cancelled. The finding becomes "3 trials per case cannot certify no-harm".
3. **`make_heldout_partition.py`** (details below).
4. **`run_full_loop_fixed_n.py`:**
   - new freeze and configuration pins;
   - a non-phase17 output prefix;
   - `'certified'` removed from the stop conditions;
   - a fixed-N `reconcile()`;
   - a count of every certified attempt;
   - distinct-hash accounting;
   - pinned completion.md sha;
   - spend guard at $150.

   Also `run_heldout2_check.py`, re-pinned, with scripted routing.
5. **Challenger.run:** an optional `actor_context_protocol` argument (default None keeps current behaviour), and an author guard that refuses `manual-reference` policies outside the probe. Both are for Phase 26.
6. **v5** in progress.py, only if Phase 21 passed, with tests.
7. **Phase 25 guard-calibration script:** every guard must false-block 10% of the time or less under the null, using stored v4 trials.
8. **A $0 fake-worker test** of the Phase 16 evidence re-read, plus a pre-declared trigger: 2 or more first-read failures in about 400 episodes starts a patience-loop build later.

**heldout-2 construction rule** (committed in Phase 20; see the amendment under Phase 20 step (b): the committed text, with its draw spaces fixed, is `PHASE20_EXPERIMENT.md` Appendix A, and only the seed moves to Phase 22):
- Six cases: no fault, delayed confirmation response (F1 send_confirmation, above the 1.0 s timeout), delayed upgrade success (F2 SUCCEEDED, d in 1..4), delayed refusal (F2 FAILED, within reach), stale history (F3), and transient upgrade failures (F4 update_order, count 2..4).
- occurrence = 1, and parameters drawn uniformly by the committed seed.
- Novelty: exclude identities that appear in completion manifest 7ab9368e or in the promotion partition. The comparison runs in code and prints nothing; excluded draws are re-drawn deterministically. The no-fault case is exempt.
- The final-audit file is not loaded, because it is untouchable. Possible overlap is disclosed.
- Disclosure: heldout-2 is held out from the checked policy's generation and selection, not unseen by the operators.
- Nobody opens the file.
- No development sweep or challenge of a new policy runs before its heldout-2 verdict.

**$0 validity track** (only while no paid run is active):
- The yield-1 soak as a 2x2 (old or new api.py × old or new business_tools.py, about 300 episodes per cell, scratch store, worlds and port). The primary read-out is whether the old code loses requests end to end.
- P5: 300 isolated runs, 100 runs of the test file, 40 full-suite runs, and a loaded-CPU arm.

**Days:** 5, with two review rounds (pitfall 74). **Output:** the frozen configuration hash, the sealed manifest_hash, and a decision on v2.

### Phase 23: fixed-N full loop

**Question.** On the fixed lab, with the byte-identical brief, v4 and the Phase 17 settings, how often does a fresh study certify a completion repair?

**Design.** 30 attempts, fixed in advance, with no stop at a success. It stops only at N, the $150 spend guard (reported as "truncated at n=j"), or 5 consecutive infrastructure failures.

**Read-outs.**
- Primary: k of 30 with a Wilson interval.
- Secondary: pooled (k+1)/39, with the caveat that Phase 17 stopped at its first success.
- The stage funnel: step present vs step that actually fires, source gate, validation acceptance on clean vs dirty batches.
- Distinct hashes, with re-draws of dd62c857 counted but never re-checked.
- Controls stops, the untriggered rate, and cost per certification.

**Routing.** The first new certified hash by attempt order goes to Phase 24 by script. Only that one.

**Estimate.** P(k≥1) is 0.79 to 0.99 at 5-15% per attempt.

**Meaning.**
- k≥1: the loop reproduces on the fixed lab.
- k=0: rare, under about 11% per study, and the funnel names the stage that loses it.

**Cost.** Expected $81-100, cap $150. **Days:** 1.

### Phase 24: one held-out check of the first new certified repair on heldout-2

**Design.**
- v2 as primary; 15 trials per arm on each of the 5 fault cases and 3 on the no-fault case (156 episodes).
- At most 3 attempts, and only INCOMPLETE attempts are replaced.
- Any drift is reported. Rule 1 still fires on a failure in a drifted episode.

**Estimates.**
- P(verdict within 3 attempts) is 0.74 to 0.98, depending on the lapse rate of 3% down to 0.65%.
- P(NO_HARM) for a policy with no real effect is about 0.7. Rule 1 alone is about 14% at a 0.19% per-episode failure rate; 78 candidate episodes make it a stricter safety test than Phase 18's 18.

**Meaning.**
- NO_HARM: the first positive held-out no-harm result for any generated repair. Quote it as "0 of 78 → per-episode failure rate 3.8% or less (one-sided 95%)" plus the per-case detectable loss. Never "safe", never ACCEPTED.
- HARM by rule 1: a real failure on the fixed lab.
- HARM by rule 3 or 4: the mechanism is traced from events (policy vs lapse).
- INCOMPLETE: report it; there is no 4th attempt.

**Cost.** 156 × 8 × $0.0209 × 1.1 = $28.7 per attempt, cap $87. **Days:** 1-2.

### Phase 25: dd62c857 on the fixed lab, with a v5 lapse A/B if Phase 21 passed

**Design (if Phase 21 passed).**
- 10 v4 replays and 10 v5 replays, interleaved ABBA.
- Primary: lapse rate per exposed episode. Success requires v5 at no more than 1/3 of v4 and one-sided Fisher p < 0.05.
- Power: 0.86, 0.59 or 0.22 if v5's lapse rate is 0.3%, 0.8% or 1.5%. A non-significant result at about 1.5% reads as "not shown", not "no effect".
- Guards are the calibrated ones from Phase 22. G1 is replaced by an in-window report-wording guard, and the source-gap guard is kept.
- v4-arm co-primaries: candidate C1-C8 failures over all L episodes (Wilson upper bound), and the outcome of every executed notification step on lost-notification-response.
- Clean-batch acceptance is read by Wilson bounds and needs 8 or more clean batches. It will probably read UNCLEAR at this n, and that is stated now.

**If Phase 21 failed.** 12 v4 replays, cap $60. Run it only after Phase 24, and only if the reserve is healthy.

**Adoption.** v5 becomes the recommended configuration for later loops. It is not used anywhere in this program's main line.

**Days:** 2.

### Phase 26: small probes (optional, cap $23)

- **(a) Explorer challenge-style probe of dd62c857** ($6).
  - Uses the existing Challenger with v4, and a relative reading declared in advance: a counterexample where B0 fails as often is a pre-existing Actor failure.
  - Reported as a probe, not as FR-017 closure.
  - The new policy is challenged only after its heldout-2 verdict.
- **(b) Second completion gap** ($7).
  - Under runtime 2 the baseline sits at about 100% SAFE_UNRESOLVED on F2 delays of 5 ticks or more.
  - A MANUAL_REFERENCE policy (wait and re-read, labelled, never shown to the Mechanic) runs against B0 at d = 5, 8 and 12, 6 pairs each. The question is whether a legal policy can complete the task there.
  - Positive means a candidate source family for post-event loops.
- **(c) Mechanic slot-2 static probe** ($10).
  - Uses v4-era `completion_proposal_inputs` only. Arms: T=0 vs T=0.7, plus a hidden-prior-candidate arm.
  - Read-outs: distinct policies that differ from slot 1, and steps that actually fire (not gated on PENDING), as a contrast with intervals.
  - A side-rule auditor runs on every output.
  - The result informs later loops only.

### Phase 27: event write-up and demo ($0)

This includes the Section 0 corrections. It also corrects "9 of 10 clean batches" to the lapse-aware figure, after checking it by query first.

## 4. The best Phase 20 and why

**Phase 20 is the paired upgrade-side development probe with the source check.** Every later decision depends on it:
- the baseline completion rates that choose predicate v2 and bound its blind spots;
- confirmation that the no-report failure is gone under v4 (this decides whether the challenge probe is worth running);
- the formal closure of the ACCEPTED path;
- the one legitimate way to follow up Phase 18's transient-upgrade hint.

It costs $28 or less, uses development cases only, and moves no freeze or hash.

**Before it spends anything:**
1. Build `run_dev_probe.py` and its tests. Pin the Phase 17 settings to configuration 0a33aa51, check ledger admission and set the spend guard to $28.
2. Write `PHASE20_EXPERIMENT.md`: settings, targets, both primaries with Holm, the floor rule, power, and the safety and source rules.
3. Commit the heldout-2 construction rule and the seed hash. *(Amended: the rule is committed in `PHASE20_EXPERIMENT.md` Appendix A; the seed and its hash move to Phase 22, before any draw.)*
4. Run the $0 identity scoping and the analytic calibration.
5. Draft the Phase 18 correction.
6. Complete one adversarial review round on the protocol and the runner.
7. Follow the runbook.

## 5. Budget

| Item | Amount |
|---|---|
| Caps: 28 + 25 + 0 + 150 + 87 + 110 + 23 | $423 |
| Reserve | $111.76 (21%) |
| Expected spend at the conservative bound | about $270 |

Phases 24, 25 and 26 are conditional. The reserve is never used to re-run anything. Any use of it needs its own declaration.

## 6. Deliberately left out

- **Any re-check of dd62c857 on a held-out partition.** Its verdict is final.
- **Re-using the original promotion partition.**
- **Spending the sealed final audit.** It needs an ACCEPTED policy (audit.py:10), none can exist, and bypassing that would fabricate promotion.
- **Learning campaigns, the ACCEPTED chain test and the selector comparison.** There is no source; revived only if Phase 20 finds a 3 of 3 failure.
- **Portability and T100's external agent.** These are blocked on an ACCEPTED policy and outside input.
- **Aria / T088.** Aria stays off by the user's decision.
- **The Llama Actor transfer.**
- **A loop under v5 in this window.** Its policies could not use heldout-2 once the first verdict is out, and there is no time for a heldout-3.
- **Evidence patience-loop changes.** Wait for the trigger.
- **Structural "don't count unsent attempts" hardening.** Detection after each run is enough for now.
- **Time-drift claims from P1.**
- **HO-2's stress cases and the v2 Fisher test at 9 trials.**

Scratch files, all in /private/tmp/claude-501/-Users-shree-Desktop-Coreweave-AGI-Hackthon/31c46f2c-a976-45ff-91d4-1214cbd5c473/scratchpad/program/:
- design_tradeoff.py
- design_tradeoff.out
- design_tradeoff2.py
- design_tradeoff2.out