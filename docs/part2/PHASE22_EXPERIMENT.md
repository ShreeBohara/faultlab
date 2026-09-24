# Phase 22 protocol — build, review twice, freeze once, seal heldout-2 ($0)

**Status: declared before any paid call. Review rounds 1 and 2 ran (round 1: four lenses; round 2,
on round 1's fixes: three lenses; every lens RUN_WITH_CHANGES). Every finding of both rounds is
applied or dispositioned in the Review log. Awaiting the review's v2 decision (§6.8), then the
freeze (§8).**

Program: `docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md`, Phase 22. Phase 22 spends **$0**. It
prepares the two paid phases after it:
- Phase 23, the fixed-N full loop (`PHASE23_EXPERIMENT.md`);
- Phase 24, one held-out check on heldout-2 (`PHASE24_EXPERIMENT.md`).

Nothing below may be acted on until all of these hold, in this order:
1. every reconciliation item in §5 is closed, the last code edit is made, and the Phase 22 tests
   are re-run **after** it (pitfall 75);
2. two review rounds are logged in the Review log, the second one on the first round's fixes
   (pitfall 74) — done: rounds 1 and 2 are logged, and round 2's fixes were re-tested after the
   last edit;
3. the review has recorded its decision on predicate v2 (§6.8) — **not yet recorded** (no round-2
   lens recorded one; the decision is the approver's, see the round-2 log).

Only then does the operator take the freeze (§8), generate the seed and seal heldout-2 (§7.4),
and fill the pins, in that order. §2 lists every place this document departs from, or
clarifies, the program.

## 1. What Phase 22 produces

| output | where | when |
|---|---|---|
| the reviewed change set (§3) | the files in §3 | before the freeze |
| a decision on predicate v2: adopted, or Phase 24 cancelled | Review log, and §6.8 | at review, before the freeze |
| one code freeze | `artifacts/phase22-2026-09-24/gate-freeze-after.json` | §8 step F4 |
| the expected `configuration_hash` for Phase 23 and 24 | pins table below | §8 step F5 |
| the generator's sha256 (`generator-sha256`), committed on the backup branch | the fenced pins block below | §8 step F6, **before** the seed exists (round 2) |
| the heldout-2 seed commitment (its sha256 only) | the fenced pins block below: a column-0 `heldout2-seed-sha256: <bare 64 hex>` line, nothing else on it | §7.4 step S2, **before** the generator runs |
| the sealed heldout-2 `manifest_hash` | the fenced pins block below (and the pins table) | §7.4 step S5 |
| the pins of both runners and both protocols | pins table below | §8 steps F7–F10 |

Nothing is run against a model or the W&B project. No service is restarted. Every number in
this document was computed read-only or by pure arithmetic.

## 2. Where this protocol departs from, or clarifies, the program

| # | program | this protocol | why |
|---|---|---|---|
| 1 | change set item 6: v5 in `progress.py` if Phase 21 passed | **not in the change set** | Phase 21 read V5_NOT_ADOPTED. This is the program's own conditional |
| 2 | "one freeze" covering items 1–8 | **items 5, 7 and 8 and the $0 validity track are not in this change set** (§3.3) | they serve Phases 25 and 26, not 23 and 24. Items 7 and 8 and the validity track touch no `backend/app` file, so they can be built later without moving this freeze. Item 5 edits `backend/app/lab/challenge.py`, which moves `algorithm_hash` and the configuration hash, so it must wait until Phase 24 has ended or been cancelled, and Phase 26 then declares its own freeze |
| 3 | Appendix A: "for case *k* and attempt *j*" | *k* is the case's **1-based** position (1–6), the same number that sets its `FaultSpec.seed` metadata (2026100000 + *k*) | Appendix A does not say whether *k* counts from 0 or 1. The generator uses 1. **Declared now, before any seed exists**, so no draw can depend on the choice. The review must confirm it (R4) |
| 4 | Appendix A's case fields | each case also carries a **salt**, HMAC-SHA256(seed, `heldout-2:salt:k`). It plays no part in any draw | without it the published `manifest_hash` could be reversed: the six spaces have 216,144 combinations, which can all be hashed in seconds. With the salt the hash says nothing without the seed, **but only until the partition's first episode** (round 1): every episode stores and serves an unsalted `scenario_hash`, from which each case's schedule can be recovered exactly. So heldout-2 is spent from its first episode (§7.3) |
| 5 | predicate v2 criterion: "v2 must match or beat v1's power … and have a lower false-HARM rate" | measured, and **not met everywhere** (§6.5–6.6) | the program expected one failure (a baseline rate near 0.1). The calibration finds that one, plus weaknesses the program did not list. They are stated plainly in §6.6, and the review decides (§6.8) |
| 6 | Phase 24: "at most 3 attempts", cap $87, "P(verdict within 3 attempts) 0.74–0.98" | kept, and the consequence is stated: under Phase 18's spend guard the $87 cap **guarantees 1 attempt, usually allows 2, and allows a 3rd only if the first two together charged ≤ $34.83** (§6.7, and `PHASE24_EXPERIMENT.md` §6.3). Round 2 corrected round 1's "at most 2 in practice": heldout-2's case-mix estimate puts two attempts at $33.85–$37.53, from about 3% below to 8% above that threshold (`prep/phase24_attempt_cost.out.json`), so a 3rd attempt is possible and the within-3 figures get equal weight | the hard worst case of one attempt is 2,496 calls = $52.17. A 2nd attempt starts only if the 1st charged ≤ $34.83, and a 3rd only if the first two together did. The estimate: $16.92 per attempt with a `dd62c857…`-like candidate, $18.38 with a baseline-like one, $18.77 scaled to Phase 18's actual charge (202 calls against 182 estimated for its mix). It depends on the routed policy's call profile |
| 7 | Phase 24: "P(NO_HARM) for a policy with no real effect is about 0.7"; "rule 1 alone is about 14% at 0.19% per episode" | replaced by the calibration's measured figures (§6.7) | 0.19% was an unsourced constant (Phase 20 Appendix B (d)). The declared pooled baseline failure rate is 1 of 781 = 0.13% [0.02%, 0.72%], which gives 9.5% for 78 candidate episodes (43% at the upper bound). **Its one event is Phase 19's clock-drift episode `8c981abc…`**, a baseline lab-defect failure (C5, C6, C8) since fixed, not an Actor failure. Without it the pool is 0 of 781 [0, 0.49%]. The declared pool is kept (Phase 20 §7.6) and the 0-of-781 figures are shown beside it everywhere (§6.3, §6.7) |
| 8 | Phase 23 secondary: "pooled (k+1)/39" | quoted **only beside** the cumulative count "*k*+1 certifications in 39 attempts" and its caveat | Phase 17's pooling rule says a certification is quoted as a running total of attempts, not a rate. The program adds a pooled rate. Both are given, never the rate alone (`PHASE23_EXPERIMENT.md` §5) |
| 9 | Phase 23: "re-draws of dd62c857 counted but never re-checked" | read as **never routed to heldout-2**. Inside Phase 23 a re-drawn `dd62c857…` still goes through its own study's source gate and validation, and pays for them | a study cannot skip a candidate without changing the loop. Its held-out verdict is what is final, not its development testing |
| 10 | Phase 23: "the first **new** certified hash" | "new" means **any policy hash without a held-out verdict**. Only `dd62c857…` has one. So T15's `ec1acaf7…` would be routed if it were re-drawn and certified | the one reading that needs no judgment at run time. The review must confirm it (R8) |
| 11 | "`run_full_loop_fixed_n.py` … pinned completion.md sha"; each runner pinned | a runner's own sha **cannot be quoted in the protocol that the runner pins** (each would change the other). Phase 23's runner sha is bound by a review record the runner reads; since round 1 so is Phase 24's (R7), which is also recorded in this document's pins table and checked by the operator | a file cannot contain its own hash, and the two shas cannot quote each other |
| 12 | $0 validity track (yield-1 soak, P5) | **not built in this change set**, and not a precondition of Phases 23–24 | the program lists it under Phase 22 but gives no gate that depends on it. It may run only while no paid run is active |
| 13 | Phase 20 §7.6: an unmeasured drawable identity takes "the rate's full range 0 to 1" | **departure (round 1, after round 0's figures were seen):** for delayed upgrade success (F2 SUCCEEDED d1 unmeasured, 1 of the 4 identities 7ab9368e leaves) and stale history (F3 `versions_back` 2 and 3 unmeasured, 2 of 3) the calibration uses the measured identities' Wilson interval | the committed 0-to-1 reading is also computed (`predicate_calibration.r1.json`, `declared_criterion.worst_case_reading.zero_to_one_…`) and **does change the literal count (corrected in round 2):** over 0 to 1 the criterion function reads both cases "met", so the power half fails on **1 of 5** (transient upgrade failures) instead of 3 of 5. That "met" is a tie at 0: the interval reaches a rate of 0, where no loss is possible, so both designs' minimum power is 0. v2 is below v1 for every rate from 0.01 to 0.14 (total loss) and 0.01 to 0.92 (halving) on both cases. The null stays strictly lower for v2 either way (worst case 4.1% against 34.4%). §6.5 gives every reading, labelled. The departure is conservative against v2 |
| 14 | program Phase 22 item 1: the partition directory "replacing `load_cases('promotion')`" | **not replaced:** a request with no partition fields still runs v1 on the promotion partition, byte-for-byte the Phase 18 check | compatibility, and the v1 path is pinned unchanged (§4). The consequence is a rule (§7.5, §10): after Phase 18, no held-out request without partition fields is made for any policy, because a verdict on the retired promotion partition would be final and would block that policy's heldout-2 check |
| 15 | Appendix A: novelty against 7ab9368e and the promotion partition | the **generator** compares against both. The backend's **check-time** guard compares against 7ab9368e only (round 1) | a check-time refusal reaches any API caller, so comparing the private promotion partition there answered, at $0, whether a named schedule is in it. **What binds the generator's output to the promotion comparison (round 2; round 1 claimed this and nothing checked it):** the generator's sha256 is committed on the backup branch at F6, before the seed exists (`generator-sha256:`), and the generator refuses to read the real partition unless its own sha256 equals that committed line (§7.2); S4 then checks that `summary.json`'s `generator_sha256` equals the pin and the file on disk (`prep/seal_summary_checks.py`); the pinned `manifest_hash` binds the case list that program wrote |
| 16 | Phase 20 §7.6: the worst case is taken "over that interval and over the kind's draw space"; by-kind rates "are mixtures and are never a per-case rate" | **departure (declared in round 2, after round 1's figures were seen):** the calibration's worst-case reading uses each kind's **pooled** Wilson interval. A sealed case is one identity, so the per-identity reading is computed beside it, with the calibration's own functions (`prep/per_identity_intervals.py` and `.out.json`) | per identity, delayed upgrade success's interval widens from [0.82, 1.0] to [0.61, 1.0] (each identity is 6 of 6) and transient upgrade failures' from [0.021, 0.234] to [0, 0.435] (1/9, 1/9, 0/9). What moves (§6.4, §6.5): delayed upgrade success's v1 worst null 27.6% → 33.9%, its worst halving power v1 0.76 → 0.65 and v2 0.63 → 0.37, v2 below v1 for rates 0.61–0.93 (was 0.82–0.93); transient's v1 worst null 30.6% → 34.2%; the whole-partition worst null v1 79.1% → 81.9% (v2 55.3% unchanged); PHASE24 §7.1's worst row, v1 P(NO_HARM \| verdict) 0.20 → 0.17. The null half is strictly lower on 5 of 5 either way |
| 17 | Appendix A: re-draw until an identity is not excluded; stop only if a whole space is excluded | the generator also stops after **1,000** re-draws of one case (`MAX_DRAW_ATTEMPTS`), writing nothing | an added stop rule (round 2 declares it; round 1 mentioned it only in §7.2). Its probability is negligible: the smallest space (3) with 2 identities excluded misses 1,000 times with probability (2/3)^1000. If it fires, Phase 22 re-declares that case in the open, as for a fully excluded space |

## 3. The change set

### 3.1 Files in the change set

| file | status | what changed |
|---|---|---|
| `backend/app/lab/heldout_check.py` | changed | Adds the v2 path (§6.1): `check_plan`, `load_partition`, `excluded_identities`, `replica_layout`, `expand_cases`, `position_trials`, `first_replica_v1`, `fisher_one_sided_less`, `rule3_v2`, `assess_heldout_v2`. Only `queue_heldout_check` and `_execute` gained a v2 branch. **v1's `harmful`, `stored_candidate_failures`, `assess_heldout` and `certified_source` are text- and AST-identical to Phase 18's** (§4). Round 1: the check-time novelty scope is 7ab9368e only (§2 row 15), and a v2 request is refused when its partition already served another policy (§7.5). Round 2: `assess_heldout_v2`'s docstring only (rule 1's precedence, §6.1); no code line changed |
| `backend/app/lab/api.py` | changed | The held-out request takes three optional fields: `partition_dir`, `manifest_hash` (64 lowercase hex) and `predicate`. The route passes them through. Leaving all three out is exactly the Phase 18 request |
| `scripts/experiments/make_heldout_partition.py` | new | The heldout-2 generator (§7.2). Round 1: writes `heldout-2.json` (R1), and reads the real promotion partition only for the committed seed (§7.2). Round 2: also only when the seed line has held that one value in the backup branch's history and the generator's own sha256 equals the committed `generator-sha256:` line; `--audit-dir` refuses any path to the real `promotion.json` and requires a synthetic document; the docstring's `manifest_hash` sentence and the 1,000-draw stop (§2 row 17) corrected |
| `scripts/experiments/phase22_predicate_calibration.py` | new | The v2 calibration, $0, read-only stores (§6.3–6.7). Output in `artifacts/phase22-2026-09-24/prep/`. Round 1 added small losses, the worst-case criterion reading, the rule-1 pool's events, the Phase 24 outcome tables and provenance; every earlier value is unchanged (`predicate_calibration.r0-to-r1.diff.txt`: 7 keys added, 0 changed, 0 removed) |
| `scripts/experiments/run_full_loop_fixed_n.py` | new | The Phase 23 runner (`PHASE23_EXPERIMENT.md`). Imports `run_full_loop.py` unchanged. Round 2: unchanged (its tests changed) |
| `scripts/experiments/run_heldout2_check.py` | new | The Phase 24 runner (`PHASE24_EXPERIMENT.md`). Imports `run_full_loop.py` unchanged, and (round 1) the pinned Phase 23 runner for its ingestion and drift checks. Round 2: the ingestion reading and `/api/readiness` are recorded, never a refusal; every check the runner adopts (in the abort path or on resume, ended or not) is compared with the declared check before its decision can be the verdict; the dry plan shows every pin's state and every pinned file's MATCH or DIFFERS |
| `backend/tests/lab/test_heldout_check.py` | extended | 20 → 75 tests (round 1) → 76 (round 2: the one-policy guard admits the same policy's second attempt and ignores other partitions). Round 1: an autouse fixture replaces the promotion partition with a synthetic one in every test, including the five Phase 18 tests that loaded the real file |
| `backend/tests/experiments/test_run_heldout2_check.py` | new | 127 tests (round 1) → 136 (round 2); 4 skip until the freeze fills their pins |
| `backend/tests/experiments/test_make_heldout_partition.py` | new | 35 tests (round 1) → 41 (round 2), generator and calibration. Synthetic seeds, stores and promotion partitions only |
| `backend/tests/experiments/test_run_full_loop_fixed_n.py` | new | 112 tests (round 1) → 114 (round 2); 5 skip until the freeze fills their pins |
| `artifacts/phase22-2026-09-24/prep/` | new (round 1), extended (round 2) | Round 1: `predicate_calibration.r1.json` and `.r1.out.txt` (the calibration re-run by the round-1 script), `predicate_calibration.r0-to-r1.diff.txt`, `v1_function_hashes.py` and `.out.txt` (§4, F4), `phase18_reassessment.py` and `.out.txt` (§4, F4), `round1-mutation/` (the mutation check of both runners' tests), `tests-round1-phase.txt` and `tests-round1-full.txt`. **Round 2 (committed commands for the operator's steps, and the round-2 evidence):** `freeze_compare.py` (F4), `calibration_diff.py` (F4), `config_hash_no_env.py` (F5), `commit_to_backup.sh` (F6, S2, S5, F11), `seal_summary_checks.py` (S4), `phase23_numbers.py` and `.out.txt` (PHASE23 §7–8), `per_identity_intervals.py` and `.out.json` (§2 row 16), `phase24_attempt_cost.py` and `.out.json` (§2 row 6), `round2-mutation/`, `tests-round2-phase.txt` and `tests-round2-full.txt` |

**Tests.** The seven Phase 22 test files (`tests/lab/test_heldout_check.py`,
`tests/experiments/test_run_heldout2_check.py`, `test_run_heldout_check.py`,
`test_make_heldout_partition.py`, `test_phase20_prep.py`, `test_run_full_loop_fixed_n.py` and
`test_run_full_loop.py`) were re-run after round 2's last edit; the result is in the Review log
and in `prep/tests-round2-phase.txt` (round 1's in `prep/tests-round1-phase.txt`). The intermittent full-suite failure
(`...reservation_released[untriggered]`, ~1 in 8 runs, unexplained since Phase 10) is still open;
the suite is never reported as unconditionally green.

**The full backend suite is red by design of an earlier phase, and F2 must say so (round 1).**
This change set moves the configuration hash (§4). The closed Phase 21 runner
(`scripts/experiments/lapse_probe.py`) correctly refuses any configuration hash but Phase 19's
`0a33aa51…`, so **17 tests of `tests/experiments/test_lapse_probe.py` fail or error** (10 failed,
7 errors), each ending in lapse_probe's `PlanningError: configuration_hash differs from the
declared Phase 19 value`. And **30 tests of `tests/experiments/test_run_dev_probe.py` skip**
("needs the Phase 19 frozen tree and the Phase 17 settings file"). A closed phase's runner is
never re-pinned. These exact ids are the expected result; any other failure, error or skip is a
finding (except the known intermittent one, reported if it appears):

- failed: `test_lapse_probe.py::` `test_live_run_refuses_a_wrong_entity_project_or_model_after_the_credential_read[change3-Actor role]`,
  `test_live_run_end_to_end_on_the_real_provider_with_a_fake_client`,
  `test_a_run_that_received_nothing_may_be_restarted_in_a_new_directory`,
  `test_an_unexpected_exception_is_recorded_with_its_traceback`,
  `test_a_crash_while_writing_the_plan_leaves_a_final_manifest_and_allows_a_new_run`,
  `test_signal_handlers_are_installed_before_the_claim_and_a_stop_in_set_up_is_recorded`,
  `test_an_operator_stop_before_the_claim_claims_nothing`,
  `test_readouts_are_recomputed_only_with_the_runs_own_harness_and_plan`,
  `test_check_pins_refuses_each_altered_pin`, `test_build_plan_refuses_when_the_precheck_fails`;
- errors: `test_lapse_probe.py::` `test_build_requests_refuses_a_prompt_that_no_longer_verifies_or_whose_control_differs`,
  `test_dry_run_verifies_every_v4_development_turn`,
  `test_precheck_changes_only_treated_turns_never_a_report_required_or_terminal_rejection_turn`,
  `test_declared_populations_and_exact_request_count`, `test_every_control_prompt_is_the_stored_request`,
  `test_treated_and_placebo_prompts_differ_from_control_by_one_declared_field`,
  `test_report_required_report_prompts_are_sent_under_control_only`;
- skipped: all 30 of `test_run_dev_probe.py`'s `frozen_only` tests.

The round-2 full run, after the last edit, is in the Review log and `prep/tests-round2-full.txt`
(round 1's in `prep/tests-round1-full.txt`). **N3, decided in round 2: option (b).** These exact
ids stay the accepted result; `test_lapse_probe.py`, a closed phase's test file, is not edited
("closed phases are closed"; round 2's statistics lens judged (b) consistent with that rule).

### 3.2 Unchanged, and pinned as unchanged

| file | sha256 |
|---|---|
| `scripts/experiments/run_full_loop.py` (the Phase 17 runner, reused by both new runners) | `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342` |
| `scripts/experiments/gate_freeze.py` | `5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190` |
| `scripts/experiments/check_clock_drift.py` | `fa25ab9d38ed1287ff530751a4157eedffb8a0692e756bce0edef64133ae956a` |
| `scripts/experiments/check_ingestion_health.py` | `edde0190836898e2a301aadbb16906ded3ae20a5f51cd51bd4c4ee7266313c02` |
| `backend/app/agents/prompts/completion.md` (the Mechanic's brief; equals the Phase 16 freeze Phase 17 ran on) | `e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673` |
| `artifacts/phase16-2026-09-22/settings-phase17.json` | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| `artifacts/phase17-2026-09-23/launch_backend.py` (the non-reload launcher) | `78911a293492b803d6c688a6044cf6e578e2b1bd6b5ccd93c65029f42aca9827` |

`backend/app/referee/checks.py` has not been opened. Its hash is taken by `gate_freeze.py`, as in
every phase since 16.

### 3.3 Not in this change set (program items 5, 7, 8 and the validity track)

| program item | serves | status | constraint |
|---|---|---|---|
| 5. `Challenger.run` optional `actor_context_protocol`, and a guard refusing `manual-reference` policies outside the probe | Phase 26 | not built | edits `backend/app/lab/challenge.py`, which moves the configuration hash. **No edit under `backend/app` until Phase 24 has ended or been cancelled.** Phase 26 declares its own freeze |
| 6. v5 | Phase 25 A/B | dropped | Phase 21 read V5_NOT_ADOPTED |
| 7. Phase 25 guard-calibration script | Phase 25 | not built | script only; does not move this freeze. Built and reviewed before Phase 25 |
| 8. $0 fake-worker test of the Phase 16 evidence re-read, and the declared trigger | later loops | not built | tests only; does not move this freeze |
| $0 validity track: the yield-1 2×2 soak; P5 (300 isolated runs, 100 file runs, 40 full-suite runs, a loaded-CPU arm) | the Phase 19 fix, the flaky test | not built | only while no paid run is active; not a precondition of Phases 23–24 |

## 4. Integrity, measured while writing this protocol ($0, read-only)

A draft freeze was taken with the unchanged `gate_freeze.py` into the scratch directory. It is
**not** the freeze: the §5 edits come after it. What it shows:

| check | result |
|---|---|
| `assess_pairs` text sha256 | `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2`, **unchanged** |
| `scorer_hash` | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e`, **unchanged** (hashed by the tool; `checks.py` not opened) |
| every `functions` and `files` entry of the freeze, against Phase 19's freeze (`3636ca21…`) | **identical** |
| every frozen function's text, against Phase 16's freeze (the code Phase 17 ran on, `96dc32a0…`) | **identical**; one frozen file differs, `evaluation.py` (Phase 18's declared `actor_context_protocol` argument) |
| fingerprints against Phase 19's freeze | **moved:** `algorithm_hash`, `runtime_hash`, `tree_lab` (both edited files are under `backend/app/lab`). **Unchanged:** `scorer_hash`, `source_hash`, `contract_hash`, `actor_prompt_hash`, `adapter_hash`, `interpreter_hash`, `service_hash`, `dependency_lock_hash`, `tree_referee`, `tree_telemetry` |
| v1 held-out functions against Phase 18's code (backup commit `f4014f0`; unchanged through `2c62d0e`) | text- and AST-identical: `harmful` `1b181c1cfce695a8e7ac9861887cf562653556d453d9bd0f4225fc82e5118620`, `stored_candidate_failures` `ad56068809ccdc6f31228c15568be008df90befccf4e19126c7e18ac4c2e01fd`, `assess_heldout` `193b63ab812f09587da8a2069fecda128049d13a2090019a42c3fb7ffa190a39`, `certified_source` `b56b6b8740bb8b42c0069f2ff38807213ca40b49712afb840a7861e2e85ee114`. The constants `SCHEMA`, `PREDICATE`, `MAX_ATTEMPTS_PER_POLICY` and `NO_REPORT_SIGNATURE` are unchanged |
| the v1 request path | a request with no partition fields gives exactly the Phase 18 record: `check_plan()` loads the promotion partition, records `partition: promotion` and its content hash, and adds no key (a test pins the key set). `queue_heldout_check`'s diff against Phase 18 is only the three keyword arguments, the plan lookup and (round 1) the one-policy guard, which runs for v2 requests only (a test pins that a v2 record naming another policy leaves the v1 request unchanged) |
| Phase 18's stored batch, re-assessed with v1 | **HARM / `check_failure`**, and the full assessment equals the stored one. Re-run after round 1's last edit to `heldout_check.py` with the committed `prep/phase18_reassessment.py` (read-only; the promotion partition is never loaded, the cases are rebuilt from the stored assessment's order with `fault_spec` unset): output `prep/phase18_reassessment.out.txt`. The four v1 hashes above were re-checked the same way with `prep/v1_function_hashes.py` against `git show f4014f0` (`prep/v1_function_hashes.out.txt`: all unchanged). Both are re-run at the freeze (§8 step F4) |
| round 1's draft freeze (scratch, after round 1's last `backend/app` edit) | again: every `functions` and `files` entry equals Phase 19's; only `algorithm_hash`, `runtime_hash` and `tree_lab` move; `assess_pairs` `783e8e58…`, `scorer_hash` `19de811c…` |
| round 2's draft freeze (scratch, after round 2's only `backend/app` edit, the `assess_heldout_v2` docstring), checked with the committed `prep/freeze_compare.py` | again: 30 `functions` and 22 `files` entries, 0 differ from Phase 19's `3636ca21…`; only `algorithm_hash` (→ `f2f71c59…`), `runtime_hash` (→ `67e6d968…`) and `tree_lab` move; `assess_pairs` `783e8e58…`, `scorer_hash` `19de811c…`, `completion.md` `e3b9362f…`. `prep/v1_function_hashes.py` (all four v1 functions and six constants unchanged since `f4014f0`) and `prep/phase18_reassessment.py` (HARM / `check_failure`, equal to the stored assessment) re-run after round 2's last edit: both exit 0 |

**Consequence:** the configuration hash moves from Phase 19's `0a33aa51…` to a new value. It is
computed once, at the freeze (§8 step F5), and pinned in both runners. Round 1's integration
review computed a draft value, `d235e428…`; round 1's own edits to `heldout_check.py` moved
`algorithm_hash` and `runtime_hash` again, so that draft is stale and nothing may quote it. Round
2's launch lens computed `d113d146…` before round 2's docstring edit, and the committed
`prep/config_hash_no_env.py` gave `2cf63e93…` after it (its `algorithm_hash` and `runtime_hash`
equal round 2's draft freeze). **Both are drafts too:** any edit under `backend/app` moves them, and
only F5's value is ever pinned.

## 5. Interface reconciliation — every item closed before the freeze

The three builders worked in parallel. Reading their code side by side shows these mismatches.
**Each one would stop Phase 23 or 24 before spending, or has already made a test kinder than
the real service (pitfall 76). None may be left to the run.**

| # | problem | evidence | required fix |
|---|---|---|---|
| **R1** | **The partition file name differs.** The generator writes `<out>/cases.json`; the backend reads `<dir>/heldout-2.json` | `make_heldout_partition.CASES_FILE = 'cases.json'`; `heldout_check.PARTITION_FILE_V2 = 'heldout-2.json'`. Both agree that `manifest_hash = content_hash(cases)` and that only the `cases` list is read | Change the generator's `CASES_FILE` to `heldout-2.json`. That keeps the tested backend untouched; the generator's tests use the constant. Add one integration test: the generator's output, built from a synthetic seed and a synthetic promotion partition, loads through `load_partition` with its printed `manifest_hash` |
| **R2** | **The Phase 24 runner reads the routing field from the wrong place.** It reads a top-level `routing`; the fixed-N runner writes it at `summary.routing` | `run_heldout2_check.PHASE23_ROUTING_FIELD = 'routing'`, read as `manifest.get('routing')`; `run_full_loop_fixed_n` writes `manifest['summary'] = summarize_fixed_n(...)`, which holds `routing`. Today Phase 24 would refuse with "declared routing differs" | Read `manifest['summary']['routing']` |
| **R3** | **The two runners disagree on which Phase 23 runs may route.** Phase 23 marks `routable: true` only when the run ended at `fixed_n` or `spend_guard` and the chosen row's post-checks passed. Phase 24 refuses only `running`, `checkpoint` or an empty stop, so it would route from a `breaker` or `aborted` run | `PHASE23_OPEN_STOPS = (None, '', 'running', 'checkpoint')`; `routing(..., final=stop_reason in FINAL_STOPS)` | Phase 24 requires `summary.routing.routable is true` and `stop_reason in ('fixed_n', 'spend_guard')`. Declared in `PHASE24_EXPERIMENT.md` §2 |
| **R4** | Appendix A does not fix whether *k* counts from 0 or 1 | the generator uses the 1-based position | Confirm §2 row 3 at review, **before the seed exists** |
| **R5** | **The Phase 24 runner's tests use a fake Phase 23 manifest that the real runner never writes:** top-level `routing`, and `stop_reason: attempt_cap` (a Phase 17 stop reason). That is why R2 and R3 pass their tests | `test_run_heldout2_check.py` lines 57–58 | Build the fake from the real `run_full_loop_fixed_n.summarize_fixed_n` and real row shapes, and test `routed_policy` on `fixed_n`, `spend_guard`, `breaker` and `aborted` manifests |
| **R6** | **Two tests assert that the shipped pins are placeholders.** They go red the moment §8 fills the pins | `test_run_heldout2_check.py:173` (`unfilled_pins() == PINS`); `test_run_full_loop_fixed_n.py:157` | Change both to assert each pin is either the placeholder or a well-formed 64-hex value, and test the refusal with `monkeypatch`. Otherwise the post-freeze test run cannot pass |
| **R7** | **Phase 24's runner sha is bound to nothing but the operator.** Phase 23's runner reads a review record that must repeat its own sha; Phase 24's has no such check, and its protocol cannot quote its sha (row 11) | `run_heldout2_check.py` has no `--review-record` | Required: the operator check in `PHASE24_EXPERIMENT.md` §9 step 4, against this document's pins table. Recommended: give the Phase 24 runner the same `--review-record` binding as Phase 23's (a code change, reviewed like any other) |
| **R8** | "New" in the routing rule | both runners exclude only `dd62c857…` | Confirm §2 row 10 at review |
| **R9** | The $87 cap funds 1 attempt for sure and usually 2; a 3rd only if the first two charge ≤ $34.83 (§2 row 6; round 2 corrected round 1's "at most 2") | `run_heldout2_check.py` dry plan: "1 attempt(s) are guaranteed and each later one needs the total so far <= $34.83" | The review decides: keep $87 with the attempt count of §2 row 6 stated (this protocol's default), or raise the cap from the reserve by a separate declaration **before** the freeze. The cap is never raised after a Phase 24 attempt |
| **R10** | Phase 24's runner leaves `DECLARED_BASE_RUNNER_SHA256` as a placeholder, although the value is known and unchanged | Phase 23's runner pins `07dcaa93…` now | Fill it at the freeze with `07dcaa93…`; any other value is a finding |

**Status after review rounds 1 and 2** (details in the Review log):

| # | status |
|---|---|
| R1 | **closed**: the generator writes `heldout-2.json` (`CASES_FILE` is `f'{PARTITION}.json'`); a cross-build test loads the generator's output through the backend's own `load_partition` under its printed `manifest_hash` and plans 78 pairs |
| R2, R3, R5 | **closed**: Phase 24 reads `summary.routing`, requires the Phase 23 stop to be `fixed_n` or `spend_guard`, requires `run_final` and `routable` true, and refuses a routed row whose post-checks do not start with `passed`. The fake Phase 23 records are built with the real `summarize_fixed_n`, and six integration tests route (or refuse) records written end to end by the real Phase 23 runner: `fixed_n`, `spend_guard`, `breaker`, `aborted`, pending post-checks, and a stop during campaign create |
| R4, R8 | **confirmed by round 2's statistics lens** (R4: the 1-based *k* agrees with Appendix A's "position (1–6)"; R8: "new" means "no held-out verdict", which matches the program's only stated reason for excluding `dd62c857…`, its finality). The approver records the confirmation at F1 |
| R6 | **closed**: both runners' tests assert each pin is a placeholder or well formed, and a separate test checks each filled pin against its file (skipped until the freeze). Round 2 found one more (C1): the Phase 23 dry-plan test counted exactly six UNFILLED rows and would have failed at F8; it now follows the shipped pins, and a filled-pins case is tested |
| R7 | **closed**, and confirmed in round 2 (the documented review-record templates pass both runners' checks; a hash copied with its trailing newline is refused) |
| R9 | the cap is a constant (`SPEND_CAP = 87.0`, no flag), so raising it is a code edit before the freeze. **Round 2's statistics lens recommends keeping $87** with the attempt count restated (§2 row 6: guaranteed 1, usually 2, a 3rd only if the first two charge ≤ $34.83). This protocol keeps $87; the approver records the decision at F1 |
| R10 | unchanged: filled at F10 (it is not a precondition of F2) |

Two runner behaviours found in review of the loop builder's work are **not** mismatches, and are
declared in `PHASE23_EXPERIMENT.md`: its `reconcile()` reads a certified row whose post-check
failed as not certified (Phase 17's read it as a discrepancy, which made such a resume
impossible), and it re-runs the process-independent post-checks when it recovers a row.
`check_ingestion_health.py` always reads `artifacts/lab.sqlite3`, which is the store both runs
use.

## 6. Predicate v2 (`faultlab-heldout-no-harm/v2`)

### 6.1 Definition (as built in `assess_heldout_v2`)

- **Shape.** Each fault case runs as 5 replicas of `PairedEvaluator`'s 3 pairs, so **15 trials
  per arm**. The no-fault case runs as 1 replica, so **3 per arm**. Six cases give 26 evaluator
  positions, **78 pairs and 156 episodes**.
- **Order.** Replica-major: the first pass runs every case once, in partition order, then four
  more passes over the five fault cases.
- **Rule 1 (unchanged from v1).** HARM (`check_failure`) if any candidate trial, paired or
  retained, retried or not, complete batch or not, failed a C1–C8 check. `harmful()` is v1's
  function, unchanged: a lab error's or stop's missing report does not count; any other failed
  check does. Stored candidate failures are recovered after a crash, cancel or restart.
- **INCOMPLETE (unchanged).** Otherwise INCOMPLETE unless every pair is valid and triggered.
- **Rule 3 (new).** On every **fault** case, pooled over its 5 replicas, for COMPLETED and
  for CORRECTLY_REJECTED separately: HARM (`lost_outcome`) if the one-sided Fisher exact
  p ≤ 0.05 for L below B0, **or** L = 0 while B0 ≥ 3. The p is computed with exact fractions and
  compared exactly.
- **Rule 4 (unchanged).** HARM (`no_fault`) if the no-fault case did not complete 3 of 3.
- **Otherwise NO_HARM.**
- **Which rule names the verdict (corrected in round 2).** Rule 1 takes precedence: when it fires
  the verdict is HARM (`check_failure`) and rules 3 and 4 are **not evaluated** (`harm_findings`
  stays empty; their counts remain in `by_case`), whatever the partition order. The same holds for
  INCOMPLETE. Otherwise every rule-3 and rule-4 finding is listed in `harm_findings`, and the
  first, in partition order, names the verdict. (v1 behaved the same way; round 1's text claimed
  more.)
- **Stored beside it, descriptive only:** pooled per-case counts, per-replica counts, the exact
  p-values, and **v1 run on the first replica of every case** (`v1_first_replica`, with
  `descriptive_only: true`). Retained lab-error trials are assigned to their replica by
  execution order; if that cannot be reconciled, v1 uses the paired trials only and says so.
- **Two facts about rule 3 at 15 trials.** The OR-branch adds exactly one cell: L 0 vs B0 3
  (Fisher p = 0.112). Fisher alone already fires at L 0 vs B0 4 (p = 0.0498). And on each case
  only one of the two outcome keys can fire in practice, because the baseline almost never
  reaches the other one there.

### 6.2 The declared criterion (program, Phase 22 item 2, declared before any Phase 20 data)

> v2 must match or beat v1's power on each harm scenario at the Phase-20-measured baseline
> rates; it must have a lower false-HARM rate under the null; the verdict states the minimum
> detectable loss per case.

Phase 20 §7.6 fixed how the rates are used: as intervals, and for rule 1 as a pooled failure
rate, never as a per-setting point estimate.

### 6.3 Calibration inputs

`scripts/experiments/phase22_predicate_calibration.py`. Round 0 ran sha256
`7e483d9f0115fddd537c0761c89ff38fc1990ca40af9bcd1e5419767a08eb2f2` (output
`prep/predicate_calibration.json` and `.out.txt`). Round 1 extended it (sha256
`143a44b5dcab07d25f6db327168993750aee116b6d5c172c8b64389465a4d562`) and re-ran it: output
`prep/predicate_calibration.r1.json` and `.r1.out.txt`. The round-1 output records its own script
sha and each input's path, size, time and sha256 (`provenance`); every value round 0 produced is
unchanged (`prep/predicate_calibration.r0-to-r1.diff.txt`). Read-only stores (the main store and
the Phase 20 run store), v4 development episodes only, baseline policy `bafdc14f…`. The rule-3
arithmetic is imported unchanged from Phase 20's `phase20_null_calibration.py`, so both phases
use one method; the Fisher test in `heldout_check.py` agrees with it on every cell of the 16×16
grid.

| heldout-2 kind | baseline target rate (valid B0 trials) | Wilson 95% | note |
|---|---|---|---|
| no fault | COMPLETED 271 of 278 = 97.5% | [94.9%, 98.8%] | |
| delayed confirmation response | COMPLETED 129 of 130 = 99.2% | [95.8%, 99.9%] | **stand-in:** the only v4-measured identity (F1 1500 ms) is in 7ab9368e, so it can never be drawn. 0 of the 1,500 identities 7ab9368e leaves are measured |
| delayed upgrade success | COMPLETED 18 of 18 = 100% | [82.4%, 100%] pooled; [61.0%, 100%] per identity (§2 row 16) | 3 of the 4 identities 7ab9368e leaves are measured (Phase 20 d2–d4, 6 of 6 each) |
| delayed refusal | CORRECTLY_REJECTED 129 of 129 = 100% | [97.1%, 100%] | **stand-in:** the only v4-measured identity (F2 FAILED d2) is in 7ab9368e. 0 of the identities it leaves are measured |
| stale history | COMPLETED 6 of 6 = 100% | [61.0%, 100%] | 1 of the 3 identities 7ab9368e leaves is measured (Phase 20 versions_back 1) |
| transient upgrade failures | COMPLETED 2 of 27 = 7.4% | [2.1%, 23.4%] pooled; [0, 43.5%] per identity (1/9, 1/9, 0/9; §2 row 16) | all 3 identities 7ab9368e leaves are measured (Phase 20 Block A); **floor-limited** there |

**What "drawable" means here (round 2).** Every count above subtracts only 7ab9368e. Appendix A
also excludes every identity of the promotion partition, which covers the same six kinds (Phase
18's public results name them), so it probably removes one identity from several of these
spaces, possibly a measured one. How many, and which, is unknowable by design: computing it would
leak the promotion partition. So these counts are upper bounds on what heldout-2 can draw, and no
probability that a sealed case is a measured identity is implied.

- **Rule-1 failure pool:** 1 of 781 = **0.13%** [0.02%, 0.72%]. This equals Phase 20's 1 of 712
  plus 0 of 69, and is the declared pool (Phase 20 §7.6).
  - **Its one event is Phase 19's clock-drift episode `episode-8c981abc…`** (B0, C5/C6/C8; listed in
    `artifacts/phase19-2026-09-23/clock-drift-and-masking-all-worlds.txt`). That is a lab defect,
    fixed in Phase 19, not an Actor failure: the drift made a truthful report fail.
  - **Without it: 0 of 781 [0, 0.49%]** (`non_defect_rule1_pool`). Every figure that depends on the
    pool is given at the declared 1 of 781 and beside it at 0 of 781.
- **Untriggered faults.** Only the delayed-confirmation case can realistically go untriggered:
  its F1 fires only when the Actor sends a confirmation, and the Actor's confirmation lapse
  leaves it untriggered. Measured on its stand-in identity, **8 of 264 = 3.0%** [1.5%, 5.9%],
  both arms. The notification-side family rate is 48 of 1,395 = 3.4% [2.6%, 4.5%]. The
  upgrade-side kinds are effectively zero: none of 2,595 v4 episodes skipped `get_order` or
  `update_order` (upper bound 0.15%).

### 6.4 Rule 3 per fault case, v2 against v1

Point value at the measured rate; worst over the kind's **pooled** Wilson interval in brackets
(§2 row 16; the per-identity values are given below the table). "Power" is the chance rule 3 fires
when the candidate truly loses. MDL is the smallest absolute drop in the target rate that rule 3
detects with 80% power. The **criterion** column is the worst value over that interval (the null's
maximum against each power's minimum), with round 1's departure for unmeasured identities (§2 row
13); the point reading is secondary (round 1). §6.5 gives every reading of the criterion,
labelled.

| case (rate) | null false-HARM, v1 / v2 | power, total loss, v1 / v2 | power, halving, v1 / v2 | MDL at 80%, v1 / v2 | criterion, worst over the interval |
|---|---|---|---|---|---|
| delayed confirmation (0.992) | 2.2% [10.7%] / 0.0% [0.2%] | 1.00 / 1.00 | 0.87 [0.84] / 0.97 [0.89] | 0.42 [0.43] / 0.36 [0.41] | **met**: null strictly lower; power matched or beaten |
| delayed upgrade success (1.0) | 0.0% [27.6%] / 0.0% [2.1%] | 1.00 [0.99] / 1.00 | 0.88 [0.76] / 0.98 [0.63] | 0.42 [0.46] / 0.34 [0.50] | null strictly lower; **power fails on halving** (v2 below v1 for rates 0.82–0.93) |
| delayed refusal (1.0) | 0.0% [7.7%] / 0.0% [0.1%] | 1.00 / 1.00 | 0.88 [0.85] / 0.98 [0.92] | 0.42 [0.43] / 0.34 [0.39] | **met** |
| stale history (1.0) | 0.0% [33.9%] / 0.0% [2.2%] | 1.00 [0.94] / 1.00 | 0.88 [0.65] / 0.98 [0.37] | 0.42 [0.47] / 0.34 [0.50] | null strictly lower; **power fails on halving** (v2 below v1 for rates 0.61–0.93) |
| transient upgrade failures (0.074) | 16.7% [30.6%] / 3.0% [4.1%] | **0.21 [0.06] / 0.09 [0.003]** | **0.19 [0.06] / 0.05 [0.003]** | none / none | null strictly lower; **power fails on both** |
| no fault (0.975), rule 4 | 7.4% / 7.4% | 1.00 / 1.00 | 0.88 / 0.88 | 0.40 / 0.40 | rule 4 is unchanged, so **identical**: equal, not lower |

**Per identity (round 2, §2 row 16; `prep/per_identity_intervals.out.json`).** Only two rows move.
Delayed upgrade success, over [0.61, 1.0]: null v1 [33.9%] / v2 [2.2%]; power on halving v1 [0.65] /
v2 [0.37], with v2 below v1 for rates 0.61–0.93; MDL v1 [0.47] / v2 [0.50]. Transient upgrade
failures, over [0, 0.435]: null v1 [34.2%] / v2 [4.1%]; both designs' worst power is 0, because the
interval reaches a rate of 0 where no loss exists, and v2 is below v1 for every rate from 0.004 to
0.14 (total loss) and to 0.435 (halving). The other three rows are unchanged (one identity each, or
a stand-in).

Over every possible baseline rate, rule 3's null false-HARM is at most **34.4% for v1** (at a
rate of 0.5) and **4.1% for v2** (at 0.12). (Round 0 printed the no-fault MDL as 0.39; on the
calibration's own 0.01 grid a drop of 0.39 gives 79.998% power, so it is 0.40.)

**Small losses on the high-rate cases (round 1; `small_losses` in the r1 output).** Neither the
program nor round 0 tested them. Rule 3 alone, per complete batch:

| baseline rate | null, v1 / v2 | d = 0.1, v1 / v2 | d = 0.2, v1 / v2 | d = 0.25, v1 / v2 | v2 ≥ v1 from d | MDL at 50%, v1 / v2 | MDL at 80%, v1 / v2 |
|---|---|---|---|---|---|---|---|
| 1.0 (upgrade success, refusal, stale history) | 0 / 0 | **0.27 / 0.06** | **0.49 / 0.35** | **0.58 / 0.54** | 0.28 | **0.21 / 0.24** | 0.42 / 0.34 |
| 0.992 (delayed confirmation) | 2.2% / 0.0% | **0.28 / 0.06** | **0.49 / 0.35** | **0.58 / 0.52** | 0.29 | 0.21 / 0.25 | 0.42 / 0.36 |
| 0.975 (the no-fault rate; a plausible lapse ceiling on any case) | 6.8% / 0.03% | 0.31 / 0.08 | 0.50 / 0.33 | 0.59 / 0.48 | 0.34 | 0.20 / 0.26 | 0.43 / 0.39 |

- **v2's detection floor.** With the baseline at 15 of 15, rule 3 v2 fires only when the candidate
  completes 11 or fewer. It cannot see a loss of 1 to 3 of 15. (At 14 of 15 it needs 9 or fewer; at
  13 of 15, 7 or fewer.)
- At rate 1.0 both nulls are exactly 0, so v1 is simply stronger against any loss below 0.28. At
  0.975 it is a trade: v1's extra power at d = 0.1 (+23 points) costs 6.8 points of null.
- The program's own scenario, a 0.97 rate that drops to 0.6: v1 0.75, v2 0.77.

### 6.5 The criterion, read literally (relabelled in round 2)

Phase 20 §7.6 fixed the reading: the worst value over the interval (the null's maximum, each
power's minimum), with an unmeasured drawable identity taking the rate's full range 0 to 1. Round
1 departed from that after round 0's figures were seen (§2 row 13), and the calibration's interval
is the kind's pooled one (§2 row 16). So there are three readings. **All three give the same
answer on the null and the same overall verdict; they differ in how many cases the power half
fails literally.**

| reading | where | null half | power half fails, literally | notes |
|---|---|---|---|---|
| **(a) round 1's departure**: measured identities' pooled interval | `declared_criterion.worst_case_reading` (r1) | strictly lower on 5 of 5 | **3 of 5**: transient upgrade failures (total loss and halving), delayed upgrade success (halving), stale history (halving) | conservative against v2; the reading round 1 headlined |
| **(b) the committed reading**: 0 to 1 for the unmeasured drawable identities of delayed upgrade success and stale history | `…worst_case_reading.zero_to_one_for_unmeasured_drawable_identities` (r1) | strictly lower on 5 of 5 (worst v2 4.1% against v1 34.4% on both) | **1 of 5**: transient upgrade failures | on the other two cases "met" is a tie at 0: the interval reaches a rate of 0, where no loss exists, so both designs' minimum power is 0. v2 is below v1 for rates 0.01–0.14 (total loss) and 0.01–0.92 (halving) there |
| **(c) per identity** (round 2) | `prep/per_identity_intervals.out.json` | strictly lower on 5 of 5 | **2 of 5**: delayed upgrade success and stale history (halving) | on transient upgrade failures "met" is the same tie at 0 (the 0-of-9 identity's interval reaches 0); v2 is below v1 for rates 0.004–0.14 (total loss) and 0.004–0.435 (halving) |

- **The null half is met strictly on 5 of 5 fault cases in every reading.** Round 0's "0 = 0 tie on
  three cases" was a point-estimate artefact at a rate of exactly 1.0.
- **The power half fails in every reading.** Literally it fails on 1, 2 or 3 of 5 cases depending
  on the reading; where a reading says "met", it is only because both minima are 0 at a rate where
  no loss is possible. In substance, v2 is below v1 against a halving over most of each of those
  intervals, and against a total loss on the transient case.

So the criterion is **not met** under any reading. The program anticipated only the transient
case. And the criterion's two scenarios (total loss, halving) are both losses of at least 0.5;
**against smaller losses on the high-rate cases v2 is weaker than v1** (§6.4, §6.6 item 9), which the
criterion never asked about.

### 6.6 Where v2 is weaker — plainly

1. **Transient upgrade failures (baseline 2 of 27).** v2 detects a total loss 9.5% of the time
   against v1's 20.6%, and a halving 5.4% against 18.6%. Rule 3 can fire there only if the
   baseline completes at least 3 of 15, which happens about 9.5% of the time. **No design with
   15 or fewer trials fixes this.** Context, not a re-declared criterion: v1's figure is almost
   all false alarm. Its power (0.21) barely exceeds its null rate (0.17), so neither design
   can see a loss on this case. It is **floor-limited in both**, and every verdict must say so.
2. **Halving on delayed upgrade success and stale history, over their intervals.** Both
   baseline rates are 1.0 on 18 and 6 trials. If the true rate is 0.82–0.93 (upgrade success,
   pooled interval; **0.61–0.93 per identity**, §2 row 16, since each identity is only 6 of 6) or
   0.61–0.93 (stale history), v1 detects a halving more often than v2.
3. **"Lower false-HARM" is a tie only at a point.** On delayed upgrade success, delayed refusal
   and stale history both designs are 0 at a rate of exactly 1.0. Over each interval (the declared
   reading) v2 is strictly lower on all three (§6.5).
4. **The whole-partition false-HARM is lower for v2 only while the per-trial failure rate stays
   under 0.29%.** v2 runs 78 candidate episodes against v1's 18, so rule 1 grows from 2.3% to
   9.5% at the declared pool's rate, and from 12.2% to 43.2% at its upper bound. At that upper
   bound v2's whole-partition null is 48.9% against v1's 33.6%. This is the other face of a
   stricter safety test (0 failures in 78 bounds the per-episode failure rate at 3.8%, against
   15.3% for 0 in 18), but it is a weakening in the false-alarm sense and is stated as one.
   - **The declared pool's only event is the Phase 19 drift episode** (§6.3). At 0 of 781 the
     whole-partition null is v1 24.5%, v2 10.2%; at that pool's upper bound (0.49%) v1 30.8%,
     v2 38.7%. So the 0.29% crossover sits inside the non-defect interval too, but the point
     estimate that decides it is a lab defect.
5. **Rule 4 is not improved.** The no-fault case stays at 3 trials and 7.4% null false-HARM.
6. **Far fewer verdicts per attempt, for a harmful policy too.** The delayed-confirmation case
   puts 30 trials at risk of the lapse instead of 6, so an attempt is fully triggered only
   **~40%** of the time (v1: ~83%). Every power figure in §6.4 is per **complete** batch. The $87
   cap guarantees 1 attempt, usually allows 2, and allows a 3rd only if the first two charge
   ≤ $34.83 (§2 row 6; round 2 corrected "at most 2"). P(a verdict) for a policy with no effect is
   **0.70 within 2 attempts and 0.84 within 3** at the measured lapse rate (v1: 0.97 and 1.00),
   0.65 and 0.80 at the family rate, and 0.43 and 0.57 at the upper bound; and against **every**
   harm scenario the calibration lists, v2 is less likely than v1 to deliver HARM (§6.7): a total
   loss on a high-rate case reads HARM 0.70 within 2 and 0.84 within 3, against 0.97 and 1.00 for
   v1; the shortfall becomes "no verdict", not NO_HARM.
7. **v2 drops v1's rule 3 on the no-fault case.** Rule 4 already covers its completions, and a
   CORRECTLY_REJECTED comparison is meaningless where nothing is refused. The only difference
   it can make: a baseline no-fault CORRECTLY_REJECTED with none in L would be HARM under v1 and
   not under v2.
8. **Two kinds have no measured rate at all** (delayed confirmation, delayed refusal): the
   novelty rule guarantees their only measured identities are never drawn. Their figures are
   stand-ins. Two more are only partly measured (delayed upgrade success, stale history: §2 row
   13): their figures hold only if the sealed draw is a measured identity (of the identities
   7ab9368e leaves, 3 of 4 and 1 of 3 are measured; the promotion partition, which covers the same
   six kinds, may exclude more, and which ones is unknowable by design, so no probability that a
   draw is measured is implied; §6.3).
9. **Small losses on the high-rate cases (round 1).** At a baseline of 15 of 15, v2 fires only if
   the candidate completes 11 or fewer, so it cannot see a loss of 1 to 3 of 15. At the point
   rates (1.0 on three cases, 0.992 on one) v1 has the same zero or near-zero null and **more power
   against any absolute loss below about 0.28** (d = 0.1: 0.27 against 0.06; d = 0.2: 0.49 against
   0.35). "Smaller detectable losses" holds only at 80% power; at 50% power v2 needs the larger loss
   (0.24 against 0.21 at a rate of 1.0). At 0.975 it is a trade-off, not a dominance (§6.4).
10. **One kind of harm on the delayed-confirmation case can only read INCOMPLETE.** A policy that
    stops the Actor sending the confirmation leaves F1 untriggered; `valid_trial` needs a triggered
    fault, so the pair is invalid and rule 3 never sees that loss there. On the stand-in identity the
    store already shows more untriggered trials under candidate policies (L 6 of 132) than under the
    baseline (2 of 132): descriptive, one-sided Fisher p = 0.14. Phase 24 therefore reports
    untriggered trials by case and arm for every attempt (the runner stores them), and an L-heavy
    count there is reported as a possible harm the predicate cannot score.

### 6.7 Where v2 is stronger, and the whole-partition figures

- **Rule 3's false alarms nearly disappear:** at most 4.1% per case over every rate, against
  up to 34.4%.
- **Halving power at the measured rates:** 0.97–0.98 against 0.87–0.88 on the four high-rate
  cases.
- **Detectable losses depend on the power asked for (round 1):** at 80% power v2 detects smaller
  losses on the high-rate cases (0.34–0.36 against 0.42); at 50% power it needs larger ones (0.24
  against 0.21 at a rate of 1.0), and below a loss of about 0.28 v1 is the stronger test (§6.6
  item 9).
- **A stricter safety test:** 78 candidate episodes instead of 18.
- **Far fewer false NO_HARM against a real loss:** against a halving on a high-rate case, P(NO_HARM)
  falls from 0.09 (v1) to 0.01 (v2), within 2 attempts and within 3 alike. This is where v2 genuinely
  wins.

| whole partition, policy with **no** effect | v1 | v2 |
|---|---|---|
| P(HARM) on a complete batch, measured rates, declared rule-1 pool (1 of 781) | 26.2% | **18.7%** |
| same, rule-1 rate 0 (the non-defect pool, 0 of 781) | 24.5% | 10.2% |
| same, rule-1 rate at the declared pool's upper bound 0.72% | 33.6% | 48.9% |
| same, rule-1 rate at the non-defect pool's upper bound 0.49% | 30.8% | 38.7% |
| same, worst over every interval (pooled; per identity, §2 row 16) | 79.1% (81.9%) | 55.3% (55.3%) |
| per attempt: all pairs triggered (lapse 3.0%) | 83% | **40%** |
| P(a verdict) within 2 attempts, lapse 3.0% / 3.4% / 5.9% / 0.65% | 0.97 / 0.97 / 0.91 / 1.00 | **0.70 / 0.65 / 0.43 / 0.97** |
| P(a verdict) within 3 attempts, same | 1.00 / 0.99 / 0.97 / 1.00 | 0.84 / 0.80 / 0.57 / 1.00 |
| **P(NO_HARM \| a verdict)**, lapse 3.0%, declared pool (1 of 781) | **0.73** | **0.71** |
| P(NO_HARM \| a verdict), lapse 3.0%, non-defect pool (0 of 781) | 0.75 | 0.90 |

At the declared pool, v2's P(NO_HARM | a verdict) for a harmless policy is **no better than
v1's** (0.71 against 0.73); v2 is better only if the pool's one lab-defect event is set aside
(0.90 against 0.75).

**A harmful policy (round 1; `phase24_outcomes.harmful_policy`).** One case's candidate rate
changes and nothing else; lapse 3.0%, declared rule-1 pool; NO_HARM / HARM / no verdict:

| harm | rule 3 per complete batch, v1 / v2 | within 2 attempts, v1 | within 2 attempts, v2 | within 3, v1 | within 3, v2 |
|---|---|---|---|---|---|
| stale history, total loss (1.0 → 0) | 1.00 / 1.00 | 0.00 / **0.97** / 0.03 | 0.00 / **0.70** / 0.30 | 0.00 / 1.00 / 0.00 | 0.00 / 0.84 / 0.16 |
| stale history, halving (1.0 → 0.5) | 0.88 / 0.98 | **0.09** / 0.88 / 0.03 | **0.01** / 0.69 / 0.30 | 0.09 / 0.90 / 0.00 | 0.01 / 0.83 / 0.16 |
| stale history, d = 0.2 (1.0 → 0.8) | 0.49 / 0.35 | 0.37 / 0.61 / 0.03 | 0.33 / 0.38 / 0.30 | 0.38 / 0.62 / 0.00 | 0.39 / 0.45 / 0.16 |
| delayed refusal, halving and d = 0.2 | the same as stale history (both baselines are 1.0) | | | | |
| transient upgrade failures, total loss (0.074 → 0) | 0.21 / 0.09 | 0.68 / 0.29 / 0.03 | 0.47 / 0.24 / 0.30 | 0.70 / 0.30 / 0.00 | 0.56 / 0.28 / 0.16 |
| no effect (for comparison) | — | 0.71 / 0.26 / 0.03 | 0.50 / 0.20 / 0.30 | 0.73 / 0.26 / 0.00 | 0.60 / 0.24 / 0.16 |

**The trade, in plain words.** Within 2 attempts (the cap's usual reach) v2 delivers **fewer HARM
verdicts than v1 against every harm listed** (a total loss: 0.70 against 0.97), because about 60%
of its attempts are incomplete; within 3 (possible if the first two charge ≤ $34.83, §2 row 6) the
gap narrows (0.84 against 1.00) but does not close. When v2 does reach a verdict it is far less
often a false NO_HARM (a halving: 0.01 against 0.09, within 2 or 3), and far less often a false HARM
on a case where the baseline completes about a third of the time (§6.6 item 1). Against a small
loss (d = 0.2) both designs are weak, and v2 is weaker.

A "verdict" here includes rule-1 HARM on an incomplete batch, which under the null is a real
baseline-level failure landing in the candidate arm. Lab errors are not modelled, so every P(a
verdict) is slightly optimistic. `PHASE24_EXPERIMENT.md` §7 splits these into NO_HARM, HARM and
INCOMPLETE, from the same output.

### 6.8 Decision rule (declared now; applied by the review, before the freeze)

The review reads §6.4–6.7 and records one of two decisions in the Review log:

- **v2 adopted.** Phase 24 runs as declared, with v2 primary and v1 descriptive. Its verdict
  states every weakness in §6.6 that applies, and always the transient-upgrade floor.
- **v2 judged a weakening.** **Phase 24 is cancelled.** The finding is recorded as "3 trials
  per case cannot certify no-harm, and 15 trials per case with Fisher was not judged a sound
  replacement". Then:
  - no seed is generated and heldout-2 is not sealed (§7.4 is skipped);
  - Phase 23 still runs: its primary does not depend on Phase 24. Its routing field is recorded
    and unused;
  - the $87 returns to the reserve.

The review chooses between these two only. Changing v2 (its trial count, α, the OR-branch or
the cases) would be a new predicate: a new declaration, a new calibration, a new cap and its own
review. The questions the review is asked to answer are in §9. **Round 1 added two things the
decision must weigh:** v2's blind spot for small losses on the high-rate cases (§6.6 item 9), and
the harmful-policy trade in §6.7 (fewer HARM verdicts within the cap, far fewer false NO_HARM). If
v2 is adopted, a Phase 24 verdict states both. **Round 2 adds three more, which do not change any
option:** the criterion's three labelled readings (§6.5: the power half fails literally on 3, 1 or 2
of 5, and in substance in all three); the per-identity intervals (§2 row 16); and the attempt count
(§2 row 6: usually 2, possibly 3, so the within-3 column of §6.7 weighs as much as the within-2
one).

## 7. heldout-2

### 7.1 The committed rule

`PHASE20_EXPERIMENT.md` Appendix A, committed before Phase 20 spent: six cases (no fault;
delayed confirmation response, F1 `send_confirmation` 1500–3000 ms; delayed upgrade success,
F2 SUCCEEDED d 1–4; delayed refusal, F2 FAILED d 1–4; stale history, F3 `versions_back` 1–3;
transient upgrade failures, F4 `update_order` count 2–4); occurrence 1; uniform draws by an
HMAC of the seed; novelty against completion manifest 7ab9368e and the promotion partition only;
a deterministic re-draw; a stop, never a substitution, if a whole space is excluded.

### 7.2 How the generator implements it

`scripts/experiments/make_heldout_partition.py`:
- **Spaces** in Appendix A order, parameters ascending: 1, 1,501, 4, 4, 3 and 3 schedules.
  Every schedule is validated as canonical `FaultSpec` JSON, occurrence 1, on its fixture, and
  by the simulator's own `validate_schedule`.
- **Draw:** for case *k* (1-based, §2 row 3) and attempt *j* = 0, 1, 2, …, index =
  `int.from_bytes(HMAC-SHA256(seed, f"heldout-2:{k}:{j}"), "big") mod |space|`. The first *j*
  whose identity is not excluded is taken. The no-fault case is exempt.
- **Stop:** if every identity of a space is excluded, or 1,000 attempts miss (an added stop rule,
  §2 row 17), the build stops and writes nothing. Phase 22 then re-declares that case in the open.
- **Novelty sources:** completion manifest 7ab9368e, rebuilt and hash-checked; the promotion
  partition, through the referee's own digest-verified loader. The promotion partition is
  compared in code only, and no value of it is printed or written; a loading error is replaced by
  "details withheld", because the underlying error would quote the partition's values. The
  final-audit file is never loaded.
- **What the comparison still reveals (restated in round 1; round 0 said "not even a count").**
  Two outputs depend on the promotion partition, as Appendix A requires. (1) Which draws are
  taken, and so the `manifest_hash`: harmless while the seed is secret, but with a known seed it
  would answer whether chosen schedules are in the promotion partition. (2) The stop when a whole
  space is excluded: it names the case, so it reveals that the space is fully covered; Appendix A
  requires the stop and the re-declaration in the open.
- **When the real promotion partition is read (rounds 1 and 2).** Only when all of these hold, each
  checked before the partition is read:
  - the seed's sha256 equals the single column-0 `heldout2-seed-sha256:` line of this document **as
    committed at the tip of the backup branch** (read with `git show
    backup/part2-2026-09-22:docs/part2/PHASE22_EXPERIMENT.md`);
  - that line has held **only this value** in the branch's history of this document (`git log -p`;
    round 2), so a later commit replacing the seed line does not admit a second seed;
  - the generator's own sha256 equals the single `generator-sha256:` line committed there at F6,
    before the seed existed (round 2), so the program that draws is the pinned one;
  - `--out` is `artifacts/heldout2/partition`, which must not exist yet.

  Any other build must pass `--audit-dir` with a synthetic partition. There the generator refuses
  the real audit directory **and any path that is, or links to, its `promotion.json`** (compared by
  resolved path and by `samefile`, metadata only; round 2), and it refuses, with a fixed message and
  no detail, a document whose case ids do not all start with `synthetic-`, so a plain copy of the
  real file fails closed too. **A deliberate, edited and re-digested copy is not prevented**; nor is
  a rewritten branch history. So: a throwaway seed cannot probe the promotion partition by accident
  or by pointing at the real file; S2 (commit) must precede S3 (draw); and one seed per unaltered
  backup-branch history can draw, enforced while `artifacts/heldout2/partition` exists. The branch
  history is the audit trail, and it is local and not pushed, so the operator also records the seed's
  sha256 outside the repository at S2.
- **Salt:** §2 row 4.
- **Output:** a **new** directory (mode 0700, never overwritten, written through a temporary
  sibling and renamed into place), with three files, all mode 0600:
  - the partition file, `heldout-2.json` (R1, closed in round 1): **private**. Its `cases` list is
    what the backend runs. Nobody opens it;
  - `manifest_hash`: `content_hash(cases)`, the value the backend pins and checks;
  - `summary.json`: **public**. Counts, hashes and fixed disclosure text only. A test proves that
    changing the seed or the promotion file changes only its hash fields; that is safe only while
    the seed is secret, which is why the real partition is read only for the committed seed.
- **Determinism:** the same seed and sources give byte-identical files, across processes with
  different hash seeds. So a lost partition can be rebuilt exactly from the seed, and its
  `manifest_hash` will match.
- **The seed file:** exactly 32 raw bytes, refused if group or others can read it, and refused
  unless it matches `--expect-seed-sha256`. `--new-seed PATH` creates one exclusively with mode
  0600 and prints only its sha256.
- **Check-time guard:** the backend refuses a partition whose cases do not hash to the pinned
  value, sit outside the repository, have duplicate ids, lack exactly one no-fault case, or
  repeat an identity of **completion manifest 7ab9368e**. It never loads the promotion partition
  (round 1, §2 row 15): its refusal reaches any API caller before the campaign, finality or policy
  guards run, so a promotion comparison there answered at $0 whether a named schedule is in the
  private partition. A test proves that a partition naming a (synthetic) promotion schedule gets
  the same answer as one that does not, for an unknown campaign and for a policy with a verdict.

### 7.3 Disclosed now

- heldout-2 is held out from the checked policy's **generation and selection**. It is **not**
  unseen by the operators: they wrote the rule and run the generator.
- Novelty is checked against 7ab9368e and the promotion partition only, **not** the development
  store. So heldout-2 cases can be development-measured schedules: all three transient-upgrade
  identities, three of the four upgrade-success identities and one stale-history identity were
  measured in Phase 20, with baseline and `dd62c857…` results. They stay held out from any
  **new** policy's generation and selection, which is what the rule claims.
- The delayed-confirmation and delayed-refusal cases are certain to be **unmeasured** schedules
  (§6.3).
- The final-audit file is never loaded, so overlap with it is possible and unchecked.
- **The salt protects heldout-2 only until its first episode (round 1).** Every episode stores an
  unsalted `scenario_hash`, served by the episode API and, as a 10-character alias, by the
  dashboard's matrix; the seed metadata and the six spaces are public, so each case's schedule can
  be recovered exactly from its episodes. From Phase 24's first episode heldout-2 is known to
  anyone who can read the API, and it is spent. That is why it serves exactly one policy, enforced
  by the backend (§7.5), and why the dashboard stays closed for the whole of Phase 24.
- **heldout-2's episodes are never traced or logged to Weave (corrected in rounds 1 and 2).** They
  are stamped split `promotion`, and `capture_allowed()` refuses that split (`telemetry/safety.py`),
  which gates both trace spans and evaluation sessions: Phase 18's 36 held-out episodes have 0 trace
  rows. **But every Actor turn is a W&B Inference call** (`deepseek-ai/DeepSeek-V3.1`), as for every
  episode, so the Actor's prompts, which carry observations reflecting each heldout-2 schedule, are
  sent to that provider (round 2 corrected "never sent to W&B"). No optimizer reads provider logs,
  so no guarantee changes. The local store is the only **stored or traced** copy, so it is backed up
  after Phase 24 (`PHASE24_EXPERIMENT.md` §9 step 10).
  Anyone counting heldout-2 episodes must use the held-out record's `partition` field to tell
  Phase 24 from Phase 18.

### 7.4 Seed and sealing procedure (the operator, after the freeze; nobody before)

Run from the repository root. Each step is recorded in `artifacts/phase22-2026-09-24/seal/`.

**Committing to the backup branch (every commit in S2, S5 and §8 F6 and F11; round 2).** Never
`git commit` on `main`, and never check out the backup branch: `main` is checked out with
uncommitted Part 2 work, so a plain commit would land on `main` and leave the generator's gate
refusing. Use the committed script, which writes through a temporary index and moves the branch
with `update-ref`'s old-value guard, leaving `HEAD`, the working tree and the real index untouched
(rehearsed in a scratch clone in round 2):

```
artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "<message>" docs/part2/PHASE22_EXPERIMENT.md [more files]
```

The pins it commits live in this document's **fenced pins block** (at the end): one column-0 line
per pin, the value **bare 64 lowercase hex, nothing else on the line** (no backticks, no table row,
no trailing comment). The generator reads only such a line; any other form makes S3 refuse.

- **S0. Preconditions.** The review's v2 decision is "adopted". The freeze (§8 F4) is taken, and
  `make_heldout_partition.py`'s sha256 is in the fenced block's `generator-sha256:` line **and
  committed on the backup branch** (§8 F6), so the history orders: generator pin, then seed
  commitment, then seal. `artifacts/heldout2` does not exist.
- **S1. Make the seed:**
  `mkdir -p artifacts/phase22-2026-09-24/seal && mkdir -m 700 artifacts/heldout2`, then
  `./.venv/bin/python scripts/experiments/make_heldout_partition.py --new-seed artifacts/heldout2/seed > artifacts/phase22-2026-09-24/seal/seed-sha256.json`.
  It writes 32 bytes from `os.urandom` with mode 0600 and prints only `{"seed_sha256": …}`.
  **Never print, copy into a document or open the seed file itself.**
- **S2. Commit to it before any draw.** Replace `FILL-BEFORE-GENERATOR` on the fenced block's
  `heldout2-seed-sha256:` line with the bare hex (and the same value in the pins table), then
  `artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "Phase 22 S2: heldout-2 seed commitment" docs/part2/PHASE22_EXPERIMENT.md > artifacts/phase22-2026-09-24/seal/commit-s2.txt`,
  and check it:
  `git show backup/part2-2026-09-22:docs/part2/PHASE22_EXPERIMENT.md | grep -c '^heldout2-seed-sha256: [0-9a-f]\{64\}$'`
  must print `1` (save it with the commit output). **Nothing is drawn before this commit exists.**
  The commit's time comes from the local clock and the branch is local and rewritable, so the
  timestamp is **operator-attested**, not independent (round 2): the operator also sends the seed's
  sha256 to the user in a message at S2, which is a record the operator cannot rewrite later.
- **S3. Build once:**
  `./.venv/bin/python scripts/experiments/make_heldout_partition.py --seed artifacts/heldout2/seed --expect-seed-sha256 <the committed hex> --out artifacts/heldout2/partition > artifacts/phase22-2026-09-24/seal/generator-stdout.json`.
  It prints only the public summary. It refuses, before reading the promotion partition, unless every
  condition of §7.2 holds: the seed is the committed one and the line has held no other value, the
  generator is the pinned one, and the output is exactly `artifacts/heldout2/partition` and does not
  exist yet.
  - A refusal that wrote nothing (a wrong path, a mode, a pin line in the wrong form) may be
    repeated with the same seed: the output is fixed by the seed, so a repeat is not a second draw.
  - A refusal because a whole space is excluded, or 1,000 draws missed, ends the build. Phase 22
    re-declares that case in the open; nothing is substituted.
  - Once `artifacts/heldout2/partition` exists it is never regenerated. A **new seed** is never
    made after S2. If the seed file is lost before S3, that is recorded and the seal is
    re-declared in the open.
- **S4. Check without opening** (round 2: the directory's own mode, and the summary against the
  commitments):
  `ls -ld artifacts/heldout2/partition && ls -l artifacts/heldout2/partition` shows the directory
  `drwx------` and the three files `-rw-------`;
  `shasum -a 256 artifacts/heldout2/partition/heldout-2.json` equals `summary.json`'s
  `cases_file_sha256`; and
  `./.venv/bin/python artifacts/phase22-2026-09-24/prep/seal_summary_checks.py > artifacts/phase22-2026-09-24/seal/summary-checks.txt`
  exits 0. That script reads only the public files and file modes, and checks: `generator_sha256`
  equals the committed `generator-sha256:` pin and the file on disk; `seed_sha256` equals the
  committed seed line; `novelty.promotion_partition_default_path` is true and
  `novelty.final_audit_loaded` is false; the public `manifest_hash` file equals the summary's; six
  cases. Save every output. A failed check is recorded, and the seal is not accepted.
- **S5. Record the seal:** copy `manifest_hash` and `cases_file_sha256` from the public files into
  the fenced block (`heldout2-manifest-hash:`, `heldout2-file-sha256:`, bare hex) and the pins table,
  and commit with `commit_to_backup.sh "Phase 22 S5: heldout-2 sealed" docs/part2/PHASE22_EXPERIMENT.md > artifacts/phase22-2026-09-24/seal/commit-s5.txt`.
- **S6. From here on, nobody opens** `artifacts/heldout2/seed` or the partition file: no `cat`,
  editor, viewer, grep, JSON dump or agent read, and no copy outside `artifacts/` except the
  whole-directory backups. The backend reads it in code at check time. If anyone does open
  either, it is recorded in the Review log and the Phase 24 report, and the review decides
  whether Phase 24 still runs.

### 7.5 Use rules (declared now)

- heldout-2 is used for **exactly one policy**: the one Phase 23 routes by rule
  (`PHASE24_EXPERIMENT.md` §3). No other policy is ever checked on it, so there is no selection
  across policies. **Enforced by the backend (round 1):** a v2 request is refused when any held-out
  record with the same `manifest_hash` names a different policy.
- **No held-out request without partition fields, for any policy, after Phase 18 (round 1, §2 row
  14).** Such a request is still exactly the Phase 18 check on the retired promotion partition; its
  verdict would be final for that policy and would block the policy's heldout-2 check.
- **The dashboard stays closed for the whole of Phase 24**, not only for latency: it shows each
  episode's schedule alias (§7.3).
- **No development sweep, challenge, replay or probe of the routed policy** runs before its
  heldout-2 verdict.
- Once its per-case results exist, heldout-2 cannot judge any later change they could inform.
  In practice it is then retired, as the promotion partition was after Phase 18.
- No result, count or trace of heldout-2 goes into any model input, Mechanic brief or tuning
  decision.

## 8. Freeze and configuration-hash procedure

Every step runs from the repository root unless it says otherwise. Outputs go to
`artifacts/phase22-2026-09-24/`. **The order matters:** each file's sha is taken only after every
value inside it is final. Every check below has a committed command (round 2); nothing is improvised.

- **F1. Close §5.** R1–R9 closed or decided (R4, R8 and R9 are recorded by the approver, with round
  2's recommendations in §5); R10 is filled at F10. The v2 decision is recorded (§6.8). The last
  code edit is made.
- **F2. Tests after the last edit** (pitfall 75), from `backend/`:
  `cd backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs tests/lab/test_heldout_check.py tests/experiments/test_run_heldout2_check.py tests/experiments/test_run_heldout_check.py tests/experiments/test_make_heldout_partition.py tests/experiments/test_phase20_prep.py tests/experiments/test_run_full_loop_fixed_n.py tests/experiments/test_run_full_loop.py > ../artifacts/phase22-2026-09-24/tests-final.txt 2>&1`,
  then the full suite, `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs > ../artifacts/phase22-2026-09-24/tests-full.txt 2>&1`.
  The seven files must pass with exactly the 9 pin-file skips (4 Phase 24, 5 Phase 23). The full
  suite must show exactly the 17 `test_lapse_probe.py` failures and errors and the 30
  `test_run_dev_probe.py` skips listed in §3.1 (N3 decided (b) in round 2), plus the 9 pin-file
  skips, and nothing else. Report the intermittent failure if it appears; never call the suite
  unconditionally green.
- **F3. Two review rounds** logged below (done), and the v2 decision recorded (§6.8). After any fix,
  return to F2.
- **F4. Take the freeze:**
  `./.venv/bin/python scripts/experiments/gate_freeze.py > artifacts/phase22-2026-09-24/gate-freeze-after.json`,
  then `shasum -a 256` it. Before accepting it, run and save:
  - `./.venv/bin/python artifacts/phase22-2026-09-24/prep/freeze_compare.py artifacts/phase22-2026-09-24/gate-freeze-after.json > artifacts/phase22-2026-09-24/freeze-checks.txt`
    must exit 0: every `functions` and `files` entry equals Phase 19's freeze (`3636ca21…`); only
    `algorithm_hash`, `runtime_hash` and `tree_lab` differ among the fingerprints (any other
    difference is a finding, and the freeze is not accepted until it is explained); `assess_pairs`
    is `783e8e58…4aa2`, `scorer_hash` `19de811c…8f2c2e`, `completion.md` `e3b9362f…`;
  - `./.venv/bin/python artifacts/phase22-2026-09-24/prep/v1_function_hashes.py > artifacts/phase22-2026-09-24/v1-function-hashes-at-freeze.txt`
    (exit 0);
  - `./.venv/bin/python artifacts/phase22-2026-09-24/prep/phase18_reassessment.py > artifacts/phase22-2026-09-24/phase18-reassessment-at-freeze.txt`
    (exit 0: HARM / `check_failure`, equal to the stored assessment);
  - the calibration, re-run to a **new** file:
    `./.venv/bin/python scripts/experiments/phase22_predicate_calibration.py --out artifacts/phase22-2026-09-24/prep/predicate_calibration.at-freeze.json > artifacts/phase22-2026-09-24/prep/predicate_calibration.at-freeze.out.txt`,
    then
    `./.venv/bin/python artifacts/phase22-2026-09-24/prep/calibration_diff.py artifacts/phase22-2026-09-24/prep/predicate_calibration.at-freeze.json > artifacts/phase22-2026-09-24/prep/predicate_calibration.at-freeze.diff.txt`.
    **It must exit 0 (round 2):** no difference from `predicate_calibration.r1.json` outside
    `provenance`, and the script sha in `provenance` equal to the pin. `PHASE24_EXPERIMENT.md` §7
    quotes r1, so if the store has moved the figures, the freeze is **not accepted**: the change is
    explained, the protocols' figures are corrected, and the change is re-reviewed;
  - the arithmetic behind `PHASE23_EXPERIMENT.md` §7–8 is committed since round 2
    (`prep/phase23_numbers.py`, output `prep/phase23_numbers.out.txt`); re-run it and save the output
    as `phase23-numbers-at-freeze.txt` (it must equal the committed output).
- **F5. Expected configuration hash:**
  `./.venv/bin/python scripts/experiments/expected_configuration.py artifacts/phase16-2026-09-22/settings-phase17.json > artifacts/phase22-2026-09-24/expected-configuration.json`
  (the Phase 16 tool). It builds the settings with `Settings.from_env()`, which **loads the root
  `.env` in-process** (corrected in round 1; nobody opens or prints it, and the tool prints only
  non-secret fields). The value does not depend on `.env`: cross-check it with
  `./.venv/bin/python artifacts/phase22-2026-09-24/prep/config_hash_no_env.py artifacts/phase16-2026-09-22/settings-phase17.json > artifacts/phase22-2026-09-24/expected-configuration-no-env.json`
  (committed in round 2; `env_path=os.devnull`, so `.env` is never read). The two
  `configuration_hash` values must agree, and `algorithm_hash` and `runtime_hash` must equal F4's.
  Both runners check the value again on their first campaign, at $0, before any study or check
  starts.
- **F6. Pin the scripts that do not pin a protocol, and commit the generator pin before the seed:**
  the sha256 of `make_heldout_partition.py`, `heldout_check.py` and `api.py` into the pins table,
  and the generator's also into the fenced block's `generator-sha256:` line (bare hex). Then
  `artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "Phase 22 F6: generator pinned before the seed" docs/part2/PHASE22_EXPERIMENT.md scripts/experiments/make_heldout_partition.py > artifacts/phase22-2026-09-24/commit-f6.txt`
  (round 2): the generator refuses the real build unless its own sha equals this committed line, and
  this commit, **before S1**, is what orders "generator pinned, then seed" in the history.
- **F7. Fill `PHASE23_EXPERIMENT.md`'s pins** (freeze sha, configuration hash; the other values
  there are already known), log its review findings in its Review log, and replace its status
  line with `**Status: declared before any paid call; reviewed in Phase 22 rounds 1–2 and frozen
  on <UTC date>. Approval: artifacts/phase23-<run date>/review.json.**`. `<UTC date>` is filled;
  `<run date>` **stays literal** (round 2): the run date is not known when the document is frozen,
  and the runner reads whichever record `--review-record` names. Only those lines change; save
  `git diff --no-index` of the document before and after as `fill-phase23-doc.diff`. Then take its
  sha256. **Nothing edits it afterwards**: the runner pins that sha, and approval lives in the
  review record, not in the document.
- **F8. Fill `run_full_loop_fixed_n.py`'s pins:** `DECLARED_FREEZE_SHA256`,
  `DECLARED_CONFIGURATION_HASH`, `DECLARED_PROTOCOL_SHA256` (F7), `DECLARED_GATE_FREEZE_SCRIPT_SHA256`
  (`5e21c0ec…`), `DECLARED_DRIFT_CHECKER_SHA256` (`fa25ab9d…`), `DECLARED_INGESTION_CHECK_SHA256`
  (`edde0190…`). Save the diff. Re-run both runner test files (round 2 names them), from `backend/`:
  `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs tests/experiments/test_run_full_loop_fixed_n.py tests/experiments/test_run_heldout2_check.py > ../artifacts/phase22-2026-09-24/tests-after-fill-phase23.txt 2>&1`:
  all pass, the 5 Phase 23 pin-file tests now run and pass, and only the 4 Phase 24 pin-file tests
  skip. Take its sha256. Its dry plan (with `--settings` and `--expect-freeze`) must show every file
  pin `MATCH` and the configuration hash `pinned`.
- **F9. Seal heldout-2** (§7.4, S0–S5), only if v2 was adopted.
- **F10. Fill `PHASE24_EXPERIMENT.md`'s pins** (freeze sha, configuration hash, partition
  manifest hash, seed sha, Phase 23 runner sha from F8), log its review findings, and replace its
  status line the same way as in F7 (`<run date>` literal). Take its sha256; nothing edits it
  afterwards. Then fill `run_heldout2_check.py`'s seven pins (`DECLARED_BASE_RUNNER_SHA256` =
  `07dcaa93…`, R10; `DECLARED_PHASE23_RUNNER_SHA256` = F8's sha, which also binds the drift-checker
  and ingestion-check pins it reuses) and take its sha256. Save both diffs. Re-run the seven files
  of F2, now with every pin filled:
  `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs <the seven files of F2> > ../artifacts/phase22-2026-09-24/tests-after-fill.txt 2>&1`
  (from `backend/`): all pass and **no test skips** (all 9 pin-file tests run). Its dry plan,
  `./.venv/bin/python scripts/experiments/run_heldout2_check.py --out artifacts/phase24-dryrun --plan --settings artifacts/phase16-2026-09-22/settings-phase17.json --expect-freeze artifacts/phase22-2026-09-24/gate-freeze-after.json`,
  must list no `NOT FILLED` or `MALFORMED` pin and every file pin, and the public partition
  `manifest_hash` file, `MATCH` (round 2: the plan now shows them). Phase 24's approval record must
  repeat this runner sha (R7).
- **F11. Record everything** in the pins table below (and in `freeze-record.json`, the same
  values as bare hex), and commit this document with `commit_to_backup.sh "Phase 22 F11: freeze
  and seal recorded" docs/part2/PHASE22_EXPERIMENT.md docs/part2/PHASE23_EXPERIMENT.md
  docs/part2/PHASE24_EXPERIMENT.md scripts/experiments/run_full_loop_fixed_n.py
  scripts/experiments/run_heldout2_check.py > artifacts/phase22-2026-09-24/commit-f11.txt`.
- **F12. Approval records** for Phases 23 and 24 are written by the approver when each phase is
  approved (`PHASE23_EXPERIMENT.md` §9 step 0; `PHASE24_EXPERIMENT.md` §9 step 0). They repeat
  the values above. Nothing is regenerated to get past a mismatch: a mismatch means the reviewed
  state changed, and the freeze and the review are redone.

**No edit under `backend/app`, to `gate_freeze.py`, either runner or either protocol
(`PHASE23_EXPERIMENT.md`, `PHASE24_EXPERIMENT.md`) after F4, except the pin and status-line fills of
F7, F8 and F10 and their review-log lines** (corrected in round 2: round 1's "no edit after F4"
contradicted F7–F10), until Phase 24 has ended or been cancelled. After F10 nothing in them changes
at all. An edit moves the freeze or a pinned sha, and both runners refuse. This document is not
pinned by either runner; after F4 it changes only at F6, S2, S5 and F11, through
`commit_to_backup.sh`.

## 9. Review

Two rounds, before the freeze, each with independent lenses and a skeptic on every blocking
finding. Suggested lenses (the reviewer may change them):
1. **predicate integrity:** v1 unchanged; v2 as specified in §6.1; rule-1 recovery paths on the
   v2 path; the Fisher implementation; replica attribution;
2. **calibration and honesty:** §6, against the JSON output;
3. **partition sealing:** the generator against Appendix A; no leak of the promotion partition or
   the seed through any output, error message or test;
4. **runners and interfaces:** §5, with the real manifest shapes; spend guards; abort paths;
5. **protocols:** `PHASE23_EXPERIMENT.md` and `PHASE24_EXPERIMENT.md`.

**The questions the review must answer, and record:**
- Is v2 a weakening (§6.8)? In particular: does the transient-upgrade failure count as one,
  given that both designs are floor-limited there; do the interval failures on halving (§6.6
  item 2) matter; does rule 1's larger sample count as a weakening or as a stricter test (item
  4), given that the declared pool's only event is a lab defect; **does v2's blind spot for small
  losses on the high-rate cases (item 9) make it a weakening**; and, **as a trade-off** (§6.7):
  within 2 attempts (the cap's usual reach) v2 delivers fewer HARM verdicts than v1 against every
  harm listed (a total loss 0.70 against 0.97; within 3, possible if the first two charge ≤ $34.83,
  0.84 against 1.00) but far fewer false NO_HARM (a halving 0.01 against 0.09, within 2 or 3), and
  P(a verdict) for a harmless policy is 0.70 within 2 and 0.84 within 3, against 0.97 and 1.00. Is
  that trade acceptable? **Round 2 adds:** the criterion read three ways (§6.5: round 1's departure,
  the committed 0-to-1 reading and the per-identity reading) fails its power half literally on 3, 1
  and 2 of 5 cases, and in substance in all three; the per-identity intervals move the worst-case
  figures of §2 row 16. Does any reading change the decision?
- R4: is *k* 1-based? (Round 2's statistics lens: yes, it agrees with Appendix A's "position
  (1–6)".)
- R8: does "new" include T15's `ec1acaf7…`? (Round 2's statistics lens: yes, "new" means "no
  held-out verdict", the program's only stated reason for excluding `dd62c857…`.)
- R9: is the cap $87 with the attempt count stated as in §2 row 6 (guaranteed 1, usually 2, a 3rd
  if the first two charge ≤ $34.83), or raised before the freeze by a separate declaration and an
  edit of the runner's `SPEND_CAP` constant? (Round 2's statistics lens: keep $87, restated.)
- R7: round 1 added the review-record binding to the Phase 24 runner. (Round 2: confirmed.)
- N3: keep accepting the 17 `test_lapse_probe.py` failures and errors by exact id, or add a
  declared, test-only guard to that closed phase's test file? (Round 2: (b), keep the exact ids;
  §3.1.)
- I3: is the backend's one-policy guard, with the dashboard closed, enough, or must the episode,
  campaign-list and matrix routes stop serving `scenario_hash` for non-development episodes?
  (Round 2's statistics lens: the guard plus the closed dashboard is sufficient once the W&B
  wording is corrected, which round 2 did in §7.3.)

## 10. What must not happen

- No seed before the v2 decision, the freeze and the generator's pinned sha **committed on the
  backup branch** (F6). No draw before the seed's sha256 is committed. No second seed. The generator
  enforces the last two while the partition directory exists, against the backup branch's unaltered
  history (§7.2); the branch history, and the seed's sha256 recorded outside the repository at S2,
  are the audit trail.
- No generator run against the real promotion partition with any seed but the committed one, or
  by any generator but the pinned one; no `--audit-dir` pointing at the real audit directory, at its
  `promotion.json`, or at a copy of it.
- No `git commit` on `main` and no checkout of the backup branch for any Phase 22 commit: only
  `prep/commit_to_backup.sh` (§7.4).
- No held-out request without partition fields, for any policy (§7.5).
- Nobody opens the seed, the partition file, `audit/promotion.json` or any final-audit file. No
  code prints anything about the promotion partition. Tests use synthetic fixtures only.
- No change to `assess_pairs`, `checks.py`, `harmful()` or any v1 function. No change to the
  certification rule, the thresholds or α after the calibration was seen, except by a new
  declaration (§6.8).
- No paid, provider, model or W&B call in Phase 22.
- No pin regenerated to get past a mismatch.
- Nothing is called ACCEPTED, and `dd62c857…`'s Phase 18 verdict stays HARM.

## Pins (filled at the freeze and the seal; `FILL-…` until then)

| pin | value |
|---|---|
| gate freeze file | `artifacts/phase22-2026-09-24/gate-freeze-after.json`, sha256 `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1` |
| `algorithm_hash` / `runtime_hash` (moved, declared) | `f2f71c590944adf9c9dcb331a888aa5bf17a048f4cfdba29c9a05989b2f6f412` / `67e6d968f56b11a7dab574c636b24409e760f9e2c6159bfd9dae830f271bfe47` |
| expected `configuration_hash` (Phase 17 settings on the Phase 22 code) | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba` |
| `assess_pairs` text | `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2` (must be unchanged) |
| `scorer_hash` | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` (must be unchanged) |
| v1 functions | the four hashes in §4 (must be unchanged) |
| `backend/app/lab/heldout_check.py` | `857b35b85e0213a9bfc222e21e2469c4dcc1ce226b55cafdcf3d5668b6c84766` |
| `backend/app/lab/api.py` | `9c3ac4534a1f40da9c2c07e22e7a0026d0b57ca1a4f4667baf5dadc2240a2a63` |
| `scripts/experiments/make_heldout_partition.py` | `e9783440be7f73e66df0399e5a9c6c601872ad75301833cf4e69af9f1c8b08da` (before the seed exists; also the fenced block's `generator-sha256:` line, committed on the backup branch at F6) |
| `scripts/experiments/phase22_predicate_calibration.py` (the calibration that was run) | round 1: `143a44b5dcab07d25f6db327168993750aee116b6d5c172c8b64389465a4d562`, recorded in its own output's `provenance` (round 0 ran `7e483d9f…`). F4 re-runs it; a later edit means a new calibration and a new sha here |
| `docs/part2/PHASE23_EXPERIMENT.md`, pins filled | `FILL-AT-FREEZE` |
| `scripts/experiments/run_full_loop_fixed_n.py`, pins filled | `FILL-AT-FREEZE` |
| `docs/part2/PHASE24_EXPERIMENT.md`, pins filled | `FILL-AT-SEAL` |
| `scripts/experiments/run_heldout2_check.py`, pins filled | `FILL-AT-SEAL` |
| heldout-2 partition directory | `artifacts/heldout2/partition` |
| v2 decision | **adopted** (approver, 2026-09-24; see "Approver decisions" in the Review log) |

The fenced block is what the generator and `prep/seal_summary_checks.py` read from the backup
branch: every value is filled as bare 64 lowercase hex, nothing else on its line.

```
gate-freeze-sha256: 8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1
configuration-hash: 2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba
generator-sha256: e9783440be7f73e66df0399e5a9c6c601872ad75301833cf4e69af9f1c8b08da
heldout2-seed-sha256: FILL-BEFORE-GENERATOR
heldout2-manifest-hash: FILL-AT-SEAL
heldout2-file-sha256: FILL-AT-SEAL
phase23-runner-sha256: FILL-AT-FREEZE
phase24-runner-sha256: FILL-AT-SEAL
```

## Review log

### Review log — round 1 (2026-09-23): four lenses, all RUN_WITH_CHANGES

Four independent lenses, read-only and $0: **statistics** (S), **integrity and leakage** (I),
**runners** (U) and **integration** (N). Together they returned 2 blockers (both repeated by a
second lens), 11 majors and 21 minors. Every finding was applied, except where the table says
otherwise. Nothing here was run against a model, W&B or a paid service; the real promotion
partition, `.env` and `checks.py` were never opened, and no seed or heldout-2 partition was made.

Evidence for each lens is in its reviewer's scratch folder; the evidence for the fixes is in
`artifacts/phase22-2026-09-24/prep/` (listed in §3.1).

| id | severity | finding | disposition |
|---|---|---|---|
| S1 | major | v2 cannot see small losses on the high-rate cases: at B0 15 of 15 it fires only for L ≤ 11, and below a loss of about 0.28 v1 has the same zero null and more power. The calibration tested only total loss and halving; "smaller detectable losses" held only at 80% power; PHASE24 §8 would have called a v1-HARM / v2-NO_HARM disagreement "v1's noise" exactly where v1 is the stronger test | **fixed.** The calibration adds `small_losses` (d = 0.1, 0.2, 0.25 at the point rates and at 0.975; the crossover; MDL at 50% and 80%; the detection floor; the program's 0.97 → 0.6). §6.4 small-loss table and floor; §6.6 item 9; §6.7's detectable-loss bullet is now power-dependent; §6.8 says the decision must weigh it; PHASE24 §7.3, §8 ("v1 disagrees" rewritten: a possible loss below v2's floor when B0 completed 14 or more of 15) and §11. Tests: `test_v2_cannot_see_a_loss_of_one_to_three_of_fifteen_against_fifteen`, `test_small_losses_on_the_high_rate_cases_match_round_1` |
| S2 | major | every power figure is per complete batch; within the cap v2 delivers fewer HARM verdicts than v1 against every harm scenario; P(verdict) was reported only under the null | **fixed.** The calibration adds `phase24_outcomes` (null and harmful, v1 and v2, within 1, 2 and 3 attempts); §6.7 harmful-policy table and the trade stated both ways (fewer HARM within the cap; false NO_HARM against a halving 0.090 → 0.010); PHASE24 §7.4; §9's question restated as that trade-off. Test: `test_phase24_outcomes_reproduce_round_1s_phase_level_figures` |
| S3 | major | the declared rule-1 pool's only event (1 of 781) is Phase 19's clock-drift episode `8c981abc…`, a lab defect, and it drives every "measured" rule-1 headline; at the declared pool v2's P(NO_HARM \| verdict) is no better than v1's | **fixed (disclosed; the declared pool is kept).** The calibration lists the pool's failing episodes and adds `non_defect_rule1_pool` (0 of 781 [0, 0.49%]) from Phase 19's drift list. §2 row 7, §6.3, §6.6 item 4, §6.7 (0-of-781 rows; v1's P(NO_HARM \| verdict) beside v2's: 0.73 against 0.71, and 0.75 against 0.90 at 0 of 781); PHASE24 §2 row 3, §7.1, §7.2, §8's 9.5% sentence reworded, §11. Tests: the measurement and drift-list parsing tests |
| S4 | minor | the criterion column mixed point and interval readings, against Phase 20 §7.6; the worst-case reading gives null strictly lower on 5 of 5 and power failing on 3 of 5; unmeasured drawable identities got the measured identities' interval instead of 0 to 1 | **fixed.** The calibration adds `declared_criterion.worst_case_reading` (and the 0-to-1 reading for the two partly measured kinds); §6.4's criterion column and §6.5 now headline it; the partial measurement is §2 row 13 (a declared departure, with what 0 to 1 gives); PHASE24 §7.3 flags cases 3 and 5 as measured only for some draws. While applying it one round-0 cell was corrected: delayed confirmation's worst halving power for v1 is 0.84, not 0.85. Test: `test_the_worst_case_reading_fails_power_on_three_cases_and_never_the_null` |
| S5 | minor | the Phase 24 cap was an unchecked `--spend-cap` flag | **fixed** with U2 |
| S6 | minor | on the delayed-confirmation case, a policy that suppresses the confirmation send can only read INCOMPLETE; untriggered counts were reported per attempt, not by arm | **fixed.** The runner stores `untriggered_by_case` (per case, per arm) for every attempt and prints it; §6.6 item 10; PHASE24 §8, §9 step 9, §11. Test: `test_untriggered_trials_are_recorded_by_case_and_arm` |
| S-nit | nit | the no-fault MDL is 0.40 on the calibration's own 0.01 grid, not 0.39 | **fixed**: §6.4, PHASE24 §7.3; the calibration now outputs it (`no_fault_case.mdl_80pct_absolute`) |
| I1 | major | the check-time novelty guard answered, through its refusal message and before any campaign, finality or policy guard, whether a named schedule is in the private promotion partition, at $0 | **fixed (the simplest option).** `excluded_identities()` compares against the public 7ab9368e only and never loads the promotion partition; promotion novelty is the generator's (§2 row 15, §7.2); PHASE24 §4. Tests: `test_the_check_time_novelty_scope_is_the_public_completion_manifest_only`, `test_a_partition_naming_a_promotion_schedule_gets_the_same_answer_as_one_that_does_not` (unknown campaign and final verdict, via the API's own `error_response`) |
| I2 | major | the generator read the real promotion partition for any seed matching an operator-supplied hash, so a throwaway seed and the public `manifest_hash` could probe it; nothing enforced S2 before S3 or one seed; "not even a count" was too strong | **fixed.** The real partition is read only when the seed's sha256 equals the single `heldout2-seed-sha256:` line committed on the backup branch (read with `git show`) and `--out` is exactly `artifacts/heldout2/partition`, not yet existing; otherwise `--audit-dir` (synthetic) is required, and the real audit directory is refused there. §7.2 restates what the comparison reveals; §7.4 S3; §10. Tests: `test_the_real_promotion_partition_is_read_only_for_the_committed_seed`, `test_the_real_audit_directory_is_refused_as_a_synthetic_one`, `test_the_commitment_is_the_single_pin_line_on_the_backup_branch` |
| I3 | minor | every heldout-2 episode stores and serves an unsalted `scenario_hash`, so the partition is recoverable from its first episode; the one-policy rule was not enforced | **fixed in part.** The backend refuses a v2 request whose partition already served another policy (v2 only; v1 unchanged); §2 row 4, §7.3 and PHASE24 §4 corrected (the salt protects the partition only until its first episode; heldout-2 is then spent); the dashboard stays closed for the whole of Phase 24 (§7.5, PHASE24 §9 step 3, §12). **Not done:** the optional blanking of `scenario_hash` for non-development episodes in the episode, campaign-list and matrix routes. It changes routes outside the held-out routes this change set declares, and their frontend contract; with the backend guard, a closed dashboard and heldout-2 declared spent from its first episode, no second policy can be selected on a known partition. Round 2 may still ask for it. Tests: `test_a_sealed_partition_serves_exactly_one_policy`, `test_the_one_policy_rule_never_touches_the_v1_request` |
| I4 | minor | the protocols said heldout-2 episodes are traced to W&B/Weave; `capture_allowed()` refuses split `promotion`, so the store is the only copy | **fixed**: §7.3; PHASE24 §4, §9 step 1 (rationale), new step 10 (back up the store), §10 |
| I5 | minor | R2 and R3 together: a breaker or aborted Phase 23 run, or a row with pending post-checks, would route once R2 alone was fixed | **fixed** with U1 |
| I6 | minor | `--spend-cap` could be raised at run time | **fixed** with U2 |
| I7 | minor | nothing required heldout-2 to be sealed before Phase 23 spends | **fixed**: `PHASE23_EXPERIMENT.md` precondition 3 (F9 done, or Phase 24 cancelled); PHASE24 precondition 3 repeats it |
| I8 | minor | five Phase 18 tests loaded the real `audit/promotion.json` | **fixed**: an autouse fixture in `test_heldout_check.py` returns a synthetic promotion partition from both loaders and makes the referee loader refuse the real one; the test that compared with `load_cases('promotion')` compares with the synthetic length |
| U1 | blocker | Phase 24 could not route any real Phase 23 manifest (R2), would have routed breaker, aborted and pending-post-check runs once the key was moved (R3), and its tests used a manifest shape the real runner never writes (R5) | **fixed.** `routed_policy` requires stop `fixed_n` or `spend_guard`, reads `summary.routing`, requires `run_final` and `routable`, and refuses a routed row whose post-checks do not start with `passed`. Fake records come from the real `summarize_fixed_n`; six integration tests feed records written end to end by the real Phase 23 runner to `load_routing`: `fixed_n` and `spend_guard` route; `breaker`, `aborted` and pending post-checks refuse; a stop during campaign create still routes |
| U2 | major | the $87 cap was a free flag (`--spend-cap 500` accepted) | **fixed**: `SPEND_CAP = 87.0` is a constant and the flag is gone (argparse refuses it); the manifest and the declared block record it. Tests: `test_no_human_argument_can_name_the_policy_the_cap_or_the_attempts[--spend-cap]`, the spend-guard tests |
| U3 | major | a stop while `POST /api/campaigns` was in flight left a phantom row that no path labelled, counted in n, and made Phase 24's routing refuse for good | **fixed in both runners**: the row is labelled at the abort and on resume ("interrupted before its campaign was recorded"); Phase 24's `route()` passes over a row with neither a campaign nor a study; the denominator is declared (`PHASE23_EXPERIMENT.md` §2 row 11). Tests in both files |
| U4 | major | a started check that failed the identity check was not stopped, and its decision became the run's verdict | **fixed**: stopped at once (`POST /stop`), marked `identity_mismatch`, excluded from the verdict; a resume after one is refused; a check adopted on resume is identity-checked too. Tests: the parametrized identity test (asserts the stop and the null verdict), `test_resume_is_refused_after_an_identity_mismatch`, `test_a_check_adopted_on_resume_must_be_the_declared_one` |
| U5 | major | Phase 24 had no continuation, so any abort ended the phase even at $0; pins were checked only as substrings; R1 | **fixed.** `--resume --after-abort` on the same folder (declared block must be equal; final stops refused; rows resolved, checks adopted or read back, a running check waited for); the backend's held-out checks of the policy are the authority on attempts used (an attempt that created no check uses none); every pin must be 64 lowercase hex and the directory pin a plain repository-relative path, before any HTTP call; R1 fixed (N1). Tests: nine continuation tests (a $0 refusal, a transient 503, each final stop, a changed declaration, a check left running, an untracked check in the store, spend carried over, an identity mismatch, a stop during campaign create) and the malformed-pin tests |
| U6 | major | many guards in the copied main loops could be deleted without failing a test (F03, F18, F22–F29; H16–H26) | **fixed**: a test for each (spend across resume, resume reconcile, a real SIGTERM, Ctrl-C stopping the study or check, process pins before and after an attempt, the store and Aria check, the per-attempt model check, the idle wait, the unsettled stop, every file pin, the entity, an active backend, non-final Phase 23 runs). Re-checked with the round-1 mutation harness on the final runners: all 17 Phase 23 mutants and all 45 Phase 24 mutants (the reviewers' survivors, the guards they already killed, and one per guard added in round 1) now fail at least one test (`prep/round1-mutation/`) |
| U7 | major | nothing in code bound the Phase 24 runner to what was reviewed (R7) | **fixed**: a required `--review-record`, which must say `approved`, name the approver and repeat this runner's sha, the protocol sha, the freeze sha, the configuration hash, the partition `manifest_hash` and the routed policy and study, checked before any HTTP call. Tests: nine review-record cases and a missing record |
| U8 | minor | a $0 configuration refusal took one of the 30 attempt numbers and counted as an infrastructure death on resume | **declared and fixed**: the denominator is declared exactly (`PHASE23_EXPERIMENT.md` §2 row 11, §4.1); runner-side rows (the refusals and a stop during campaign create) are no longer infrastructure deaths, and the breaker skips them (§2 row 12); the funnel lists attempts without a study by reason. Tests: `test_a_runner_refusal_is_in_the_denominator_but_is_not_a_death`, `test_a_runner_refusal_neither_counts_toward_nor_resets_the_breaker` |
| U9 | minor | after an abort, the reason stayed in memory through the in-flight stop, a wait of up to 900 s and recovery | **fixed in both runners**: saved at once after the except blocks. Tests: `test_an_aborts_reason_is_on_disk_before_the_in_flight_stop_waits` (Phase 23), `test_an_aborts_reason_is_on_disk_before_the_post_abort_wait` (Phase 24) |
| U10 | minor | the re-run guard was check-then-write around a 300 s ingestion check | **fixed in both runners**: the run record is created with an exclusive `open('x')` right after the guard, other folders are re-checked after the claim, and a refused ingestion check removes the claim. Tests: the claim-before-slow-checks and lost-claim tests in both files |
| U11 | minor | two tests asserted the shipped pins are placeholders (R6) | **fixed**: each pin is a placeholder or well formed; each filled pin is checked against its file in a separate test (skipped until the freeze) |
| U12 | minor | the Phase 24 runner ran neither the ingestion check nor the drift check | **fixed**: it runs both, through the pinned Phase 23 runner (whose pins bind both scripts, and whose file sha it checks), refuses unhealthy ingestion and records the drift check in the manifest (skipped, with its command, while a check may still be running). Tests: `test_unhealthy_ingestion_refuses_before_any_campaign_or_record`, `test_the_drift_check_runs_after_the_session_and_is_recorded`, the drift and ingestion file-pin tests |
| N1 | blocker | the backend could not load the generator's output: `cases.json` against `heldout-2.json` (R1) | **fixed**: the generator writes `heldout-2.json`; `test_the_private_file_is_the_one_the_backend_loads` builds from a synthetic seed and synthetic promotion partition, loads through the backend's `load_partition` (with its real, now public-only novelty scope) under the printed `manifest_hash`, and plans 78 pairs and 156 episodes |
| N2 | blocker | the Phase 24 router and the real Phase 23 manifest do not work together (R2, R3, R5) | **fixed** with U1 |
| N3 | major | the full backend suite is red because this change set moves the configuration hash: 17 `test_lapse_probe.py` failures and errors, 30 `test_run_dev_probe.py` skips, undeclared | **declared** (option (b)): §3.1 lists the exact ids and the cause, and F2 requires exactly them. Option (a), a test-only guard in a closed phase's test file, is outside this change set and is left to round 2. R6 is closed, so the filled pins add no failure |
| N4 | minor | the v1 default on the promotion partition was kept without a declared departure | **fixed (declared; the v1 path is unchanged)**: §2 row 14, §7.5 and §10 (no held-out request without partition fields, for any policy), PHASE24 §12 |
| N5 | minor | F5 said nobody reads `.env`, but `Settings.from_env()` loads it in-process | **fixed**: F5 says so, and cross-checks the value through the no-`.env` path |
| N6 | minor | no committed tool computed the four v1 function hashes F4 requires | **fixed**: `prep/v1_function_hashes.py` (and `prep/phase18_reassessment.py`) with their outputs; F4 re-runs both |
| N7 | minor | the configuration-hash chain left out Phase 18's `1b6e5ed0…`; PHASE24's pins block had no seed line | **fixed**: `PHASE23_EXPERIMENT.md` §3.2; PHASE24 pins block. §4 also records that round 1's draft configuration hash is stale |
| N8 | minor | nothing tied the calibration's output to the script sha that produced it | **fixed**: the calibration records `provenance` (script sha, inputs' paths, sizes, times, sha256); re-run as `predicate_calibration.r1.*` with a structural diff against round 0 (7 keys added, 0 changed); F4 re-runs it to a new file and diffs it again |

**Round 1's verification, after the last edit** (outputs `prep/tests-round1-phase.txt` and
`prep/tests-round1-full.txt`):
- the seven Phase 22 test files: **410 passed, 9 skipped** (the 9 are the pin-file tests that skip
  until the freeze fills their pins: 4 in the Phase 24 file, 5 in the Phase 23 file);
- the full backend suite: **10 failed, 1150 passed, 39 skipped, 7 errors**. The 17 failures and
  errors are exactly the expected `test_lapse_probe.py` ids and 30 of the skips are exactly the
  expected `test_run_dev_probe.py` ones (§3.1); the other 9 skips are the pin-file tests above.
  Nothing else failed; the intermittent `...reservation_released[untriggered]` passed this run;
- `prep/v1_function_hashes.out.txt`: the four v1 functions and six constants are unchanged since
  Phase 18 (text and AST); `prep/phase18_reassessment.out.txt`: HARM / `check_failure`, equal to
  the stored assessment;
- a draft freeze (scratch): every `functions` and `files` entry equals Phase 19's; only
  `algorithm_hash`, `runtime_hash` and `tree_lab` move; `assess_pairs` `783e8e58…` and
  `scorer_hash` `19de811c…` unchanged;
- both runners' dry plans exit 0 and create nothing;
- the mutation check of both runners' tests: all 17 Phase 23 and all 45 Phase 24 mutants killed
  (`prep/round1-mutation/`).

**Open for round 2:** the v2 decision (§6.8, now with S1 and S2 to weigh); R4, R8 and R9; N3's
option (a) or (b); I3's optional route change. Round 2 reviews these fixes themselves (pitfall 74):
above all the Phase 24 continuation path, the review-record binding, the exclusive claims and the
generator's commitment gate, which are new code.

### Review log — round 2 (2026-09-23): three lenses on round 1's fixes, all RUN_WITH_CHANGES

Three independent lenses reviewed round 1's fixes themselves (pitfall 74), read-only and $0:
**regressions** (A), **statistics and design** (B) and **launch rehearsal** (C). Together they
returned 6 majors and 22 minors; merging the findings two or three lenses repeated (A1 = B2,
B1 = C3, A4 ≈ B6 ≈ C8, B7 = C5, A8 = C9) leaves **4 distinct majors and 18 distinct minors**. Every
finding was applied, except where the table says otherwise. Nothing here was run against a model,
W&B or a paid service; `.env`, `checks.py`, the real promotion partition, any final-audit file and
any heldout-2 partition were never opened; no real seed or partition was made (the seal rehearsal
used a throwaway seed and a synthetic novelty scope in a scratch clone, and that seed is deleted).

Each lens's evidence is in its reviewer's scratch folder (`p22/r2-regressions`, `p22/r2-design`,
`p22/r2-launch`); the evidence for the fixes is in `artifacts/phase22-2026-09-24/prep/` (§3.1).

| id | severity | finding | disposition |
|---|---|---|---|
| A1 = B2 | major | Round 1 made the ingestion check a hard refusal at the start of every Phase 24 session. The check reads only the last 120 development `ingestions` rows; heldout-2's split-promotion episodes write none (Phase 18's 36 have 0), so nothing Phase 24 does can change the reading: a degraded tail left by Phase 23 would refuse every session, fresh or resumed, for good (probe P2: 3 of 3 resumes refused). The stated rationale ("guards the provider and telemetry path") was wrong: the check touches neither | **fixed.** `run_heldout2_check.py` records the ingestion reading and `GET /api/readiness` per session and at the top level, and never refuses on either. `/api/readiness` was not adopted as a "provider-path liveness" gate, because it says itself that it does not contact the provider (`provider_access: not_checked`), and the backend already refuses a check start at $0, using no attempt, when the simulator is not ready (`require_simulator`). PHASE24 §2 row 10, §9 steps 1 and 6 (rationale corrected). Phase 23 keeps its hard gate (its studies need Weave), now with a declared remedy for a stale reading (PHASE23 §9 step 1). Tests: `test_an_unhealthy_ingestion_reading_is_recorded_and_never_refuses`, `test_a_stale_ingestion_reading_never_blocks_an_approved_resume` (P2), `test_a_readiness_read_that_fails_is_recorded_and_never_refuses` |
| B1 = C3 | major | Round 1 justified dropping the check-time promotion comparison with "the generator's sha is pinned before the seed exists and the pinned `manifest_hash` binds its output", and nothing checked that binding: no step compared the generator that built heldout-2 with the F6 pin, `gate_freeze.py` does not cover `scripts/`, and the F6 pin was first committed together with the seed, so "before" had no ordered evidence | **fixed, both ways offered.** (1) The generator refuses the real build unless its own sha256 equals the single `generator-sha256:` line committed at the backup branch's tip. (2) F6 commits this document (and the generator) to the backup branch **before S1**, so the history orders generator pin, seed, seal. (3) S4 runs the committed `prep/seal_summary_checks.py`, which checks `summary.json`'s `generator_sha256` against the committed pin and the file on disk, `seed_sha256` against the committed seed line, `promotion_partition_default_path` true, `final_audit_loaded` false, the public `manifest_hash`, and the directory and file modes (saved as `seal/summary-checks.txt`). §2 row 15 now names this as the binding. Tests: `test_the_seed_line_must_have_held_one_value_and_the_generator_must_be_the_pinned_one`, `test_the_seed_history_and_generator_pin_are_read_from_the_backup_branch`; the seal check rehearsed in a scratch clone (all checks pass) |
| C1 | major | Filling the Phase 23 runner's pins at F8 turned `test_plan_is_dry_and_shows_every_unfilled_pin` red (it asserted exactly six UNFILLED rows), so F8's own check would fail after the freeze, when no edit is allowed | **fixed.** The assertion follows the shipped pins (`== len(fixed.unfilled_pins())`), and `test_a_plan_with_every_pin_filled_shows_no_unfilled_pin` covers the filled state. F8 and F10 now name the files to re-run and the outputs to save (`tests-after-fill-phase23.txt`, `tests-after-fill.txt`). Rehearsed: a scratch shadow of the repository with all 13 runner pins filled (draft freeze, draft configuration hash, a synthetic manifest hash) gives **250 passed, 0 skipped** for the two runner test files, and both dry plans show every pin `MATCH` |
| C2 | major | "Commit this document to the backup branch" had no recipe, and a plain `git commit` would land on `main` (checked out, dirty) while the generator's gate reads only the backup branch | **fixed.** The committed `prep/commit_to_backup.sh` writes through a temporary index (`read-tree`, `hash-object -w`, `update-index --cacheinfo`, `write-tree`, `commit-tree -p`) and moves the branch with `update-ref`'s old-value guard; it checks that `HEAD` and the real index are unchanged. §7.4 now says "never `git commit` on `main`, never check out the backup branch", gives the command at F6, S2, S5 and F11, and the `grep -c` check after S2. Rehearsed in a scratch clone (`HEAD` stayed `main`, the dirty file stayed dirty, the real repository's branch stayed at `2c62d0e`) |
| A2 | minor | U4's promise had a hole: a check adopted in the abort path (a Ctrl-C while `POST /heldout-check` is in flight) was copied into the row with no identity check, and `resolve()` returned early for terminal rows, so it was never checked on resume either; its decision became the verdict (probe P1) | **fixed as proposed, and one step further.** One `check_identity()` compares every check wherever the runner first sees it (start reply, adoption after a lost reply, the abort path, resume) and marks the row `identity_checked` or `identity_mismatch` (stopping a mismatched check that is still running). `resolve()` compares any row not yet compared, even when it has ended. A decision counts as the verdict only on a row that was compared and matched (`is_verdict`). PHASE24 §2 row 9, §6.2, §9 step 6. Tests: P1 as `test_a_check_adopted_in_the_abort_path_is_compared_and_a_wrong_one_is_never_the_verdict`, its matching counterpart, `test_resolve_compares_an_ended_check_that_was_never_compared`, `test_only_a_compared_matching_check_can_be_the_verdict` |
| A3 | minor | No test showed that the one-policy guard still admits the routed policy's second attempt on the same partition (the test hit the attempt limit first); mutants M3 (refuse any same-hash record) and M5 (ignore the hash) survived | **fixed.** `test_the_one_policy_guard_admits_the_same_policys_next_attempt_and_ignores_other_partitions`: with another policy's record on another partition present, attempt 1 is admitted, ends INCOMPLETE, and attempt 2 of the same policy on the same partition is admitted. M3 and M5 now fail it (`prep/round2-mutation/heldout_check/`) |
| A4 ≈ B6 ≈ C8 | minor | (1) The real-audit-directory refusal compared directory paths only: an `--audit-dir` holding a link to (or a copy of) the real `promotion.json` passed, and a throwaway seed then read the real partition (probe G1). (2) "Only one seed can ever draw" was too strong: the gate read only the branch tip, so a later commit replacing the seed line, plus removing the partition directory, admits another seed. (3) "Timestamps the commitment" was too strong: the branch is local and unpushed, and commit times come from the local clock | **fixed.** (1) `is_real_audit_dir` also refuses any directory whose `promotion.json` resolves to, or `samefile`s, the real file (metadata only); and a document given with `--audit-dir` must be synthetic (every case id starts `synthetic-`), else a fixed refusal with no detail, so a plain copy fails closed. A deliberate, edited and re-digested copy is not prevented, and §7.2 says so. (2) The gate also requires that the seed line has held only this value in the branch's `git log -p` history of this document; §7.2 and §10 now say "one seed per unaltered backup-branch history, enforced while the partition directory exists; the branch history is the audit trail" (rehearsed in a scratch clone: a replacing commit is refused). (3) S2 and PHASE23 precondition 3 call the timestamp operator-attested, and S2 has the operator send the seed's sha256 to the user as a record outside the repository. Tests: `test_any_path_to_the_real_promotion_file_is_refused_as_a_synthetic_one` (symlink, hard link, directory symlink; G1), `test_a_copy_that_is_not_synthetic_is_refused_without_any_detail`, and the history tests above |
| A5 | minor | Round-1 guards with no killing test: (a) both runners' `if not args.resume:` before removing the claim on an unhealthy ingestion reading; (b) Phase 24 `route()`'s pass-over condition `(campaign_id or study_id)`; (c) the runner's identity constants against the backend's (the fake builds the identity from the runner's own constants, pitfall 76) | **fixed.** (a) Phase 23: `test_unhealthy_ingestion_on_a_resume_refuses_but_keeps_the_run_record`; Phase 24 no longer refuses (A1), and its tests pin that. (b) `test_a_row_with_a_campaign_but_no_study_and_no_outcome_is_never_passed_over`. (c) `test_the_runners_check_identity_is_the_backends` (predicate, partition, Actor context, excluded hash, planned pairs, attempt limit). The reviewers' surviving mutants F4, H5 and H20 now fail (`prep/round2-mutation/runners/`) |
| A6 | minor | §6.5 labelled round 1's departure "read the declared way", and §2 row 13 said the committed 0-to-1 reading "changes no headline"; under it the power half fails on 1 of 5, not 3 | **fixed, with a correction to the finding itself.** §6.5 now gives three labelled readings: round 1's departure (power fails on 3 of 5), the committed 0-to-1 reading (1 of 5) and per identity (2 of 5, B3). The 0-to-1 "met" on delayed upgrade success and stale history is a tie at 0 (the interval reaches a rate of 0, where no loss exists, so both designs' minimum power is 0); v2 is below v1 for rates 0.01–0.14 (total loss) and 0.01–0.92 (halving) there, so the power half fails in substance in every reading. The null half is strictly lower on 5 of 5 in every reading; the criterion is not met in any. §2 row 13 corrected; §6.8 and §9 carry all readings |
| A7 | minor | F4 re-ran the calibration and saved a diff against r1 with no acceptance rule, while PHASE24 §7 quotes r1 | **fixed.** F4 runs the committed `prep/calibration_diff.py`, which must exit 0 (no difference outside `provenance`, and the pinned script sha); otherwise the freeze is not accepted, the change is explained, the protocols' figures corrected, and the change re-reviewed |
| A8 = C9 | minor | PHASE24 §9 step 10 copied the live WAL-mode store file by file | **fixed.** `sqlite3 … ".backup '…'"`, then `PRAGMA quick_check` on the copy, and its sha256, both recorded in `store-backup.txt` |
| B3 | minor | The worst-case reading used each kind's pooled Wilson interval; Phase 20 §7.6 says by-kind rates are mixtures, and a sealed case is one identity. Not declared as a departure | **declared (§2 row 16) and computed beside it.** The committed `prep/per_identity_intervals.py` (pure arithmetic on r1's per-identity counts, the calibration's own functions; it first checks that its pooled column reproduces r1 exactly) gives the per-identity reading: delayed upgrade success [0.61, 1.0], transient [0, 0.435]; the moved figures are in §2 row 16, §6.4, §6.5, §6.6 item 2, §6.7 and PHASE24 §7.1 and §7.3. The calibration script itself is unchanged (its pinned sha stays `143a44b5…`), so r1 remains the reproducible reference for F4 |
| B4 | minor | "The $87 cap allows at most 2 attempts" was stated as fact; heldout-2's case mix puts two attempts within a few percent of the $34.83 threshold | **fixed.** "Guaranteed 1, usually 2, a 3rd only if the first two charge ≤ $34.83": the committed `prep/phase24_attempt_cost.py` (read-only stores) gives $16.92–$18.77 per attempt and $33.85–$37.53 for two, about 3% below to 8% above the threshold. The within-3 figures now stand beside the within-2 ones in §2 row 6, §6.6 item 6, §6.7, §6.8, §9, and PHASE24 §2 row 1, §6.3, §7.1, §7.4 and §11. R9: $87 kept (the lens's recommendation) |
| B5 | minor | The "drawable" counts subtract only 7ab9368e; the promotion partition (same six kinds) may exclude more | **fixed.** Qualified as "of the identities 7ab9368e leaves" in §6.3 (with a note that the true counts are unknowable by design and are not computed, since that would leak), §6.6 item 8, and PHASE24 §4 and §7.3; "measured only if the draw is d2–d4 / versions_back 1" no longer implies a probability |
| B7 = C5 | minor | "No edit … after F4" contradicted F7–F10, which fill pins after F4; F1 required R10 closed, but R10 is filled at F10 | **fixed.** §8's closing rule and PHASE23 §12: no edit after F4 except the pin and status-line fills of F7, F8 and F10 and their review-log lines; nothing after F10. F1: R1–R9 closed or decided, R10 at F10 |
| B8 | minor | "Every rule that fires is listed; the first names the verdict" overclaims: rule 1 returns before rules 3 and 4 are evaluated | **fixed by rewording** (§6.1, PHASE24 §5 and §8), and `assess_heldout_v2`'s docstring (a text-only edit under `backend/app`, before the freeze; no code line changed, v1 untouched). Computing rules 3–4 descriptively after rule 1 was not chosen: it would be a behaviour change for no decision |
| B9 | minor | "heldout-2's episodes are never sent to W&B/Weave" overclaims: every Actor turn is a W&B Inference call | **fixed**: "never traced or logged to Weave; the Actor's prompts are sent to the W&B Inference provider as for every episode" (§7.3, PHASE24 §4, §9 step 10, §10). No guarantee changes |
| B10 | minor | `MAX_DRAW_ATTEMPTS = 1000` is a stop rule Appendix A does not have, and the generator's docstring said `EvaluationBatch.manifest_hash` equals `manifest_hash` | **fixed**: §2 row 17 declares the 1,000-draw stop; the docstring now says the held-out record carries `manifest_hash` and `EvaluationBatch` carries `evaluated_manifest_hash` |
| C4 | minor | F2, F4 and F5 named checks with no committed command | **fixed**: `prep/freeze_compare.py` (F4; run on round 2's draft freeze: all checks pass), `prep/calibration_diff.py` (F4), `prep/config_hash_no_env.py` (F5; draft `2cf63e93…`, whose `algorithm_hash` and `runtime_hash` equal the draft freeze's), `prep/phase23_numbers.py` and its output (committed now, not at F4; it also computes the breaker figures 0.04% / 1.9% / 8.8%), and the F2 commands in full |
| C6 | minor | Phase 24's dry plan showed only whether placeholders remained, so a mistyped pin surfaced only at the live start | **fixed**: `--plan` prints each pin's state (`NOT FILLED`, `MALFORMED`, `filled`) and each pinned file's `MATCH`, `DIFFERS`, `FILE MISSING` or `not given`, including the public partition `manifest_hash` file (never the partition file). PHASE24 §9 step 5 and F10 pass `--settings` and `--expect-freeze`. Test: `test_the_plan_shows_each_pins_state_and_whether_each_pinned_file_matches` |
| C7 | minor | S4's `ls -l` did not show the directory's mode; "the pins table" was used where the generator reads only the fenced block's column-0 bare-hex line; F7's status line named a `<date>` unknown at the freeze | **fixed**: `ls -ld … && ls -l …`; §1, §7.4 and the pins section say "the fenced pins block, bare 64 hex, nothing else on the line"; F7 says `<run date>` stays literal |
| C10 | minor | The latency check runs before the backend restart, so it measures the process about to be killed | **fixed**: PHASE23 §9 steps 3–4 and PHASE24 §9 steps 3–4 re-run `loop_latency.py 20` after the restart and keep both outputs. The lens also saw the Vite dev server on :5173 and a backend older than `heldout_check.py`'s last write, both of which the runbook's existing steps (close the dashboard, restart the backend) already handle; neither service was touched here |

**Noticed while applying round 2** (no lens raised these; each is recorded, not re-declared):
- **Phase 23's ingestion gate has the same stale-reading property as Phase 24's did.** Its studies
  do write development ingestion rows, but a session refused on a degraded tail writes none, so a
  resume after such a stop is refused until other development episodes are traced. Phase 23 keeps
  the gate (round 2's statistics lens), and PHASE23 §9 step 1 now declares the remedy: the user's
  decision, never an edit of the runner, the check or its threshold.
- **Two runner mutants survive and are equivalent in effect** (`prep/round2-mutation/runners/`): the
  abort path's comparison of a started check whose comparison had not run yet (HE), and a mismatch
  also marked as compared (HI). `is_verdict` and `resolve()` already keep such a check from being
  the verdict.
- **A6's "power fails on 1 of 5" is literal only** (the tie at 0 above); §6.5 flags it.

**Round 2's verification, after the last edit** (outputs `prep/tests-round2-phase.txt` and
`prep/tests-round2-full.txt`):
- the seven Phase 22 test files: **428 passed, 9 skipped** (76 + 136 + 16 + 41 + 18 + 114 + 36 = 437;
  the 9 are the pin-file tests that skip until the freeze fills their pins);
- the full backend suite: **10 failed, 1168 passed, 39 skipped, 7 errors** (1150 → 1168 passed: the 18
  new tests). The 17 failures and errors are exactly the expected `test_lapse_probe.py` ids, and the
  39 skips are exactly the 30 `test_run_dev_probe.py` ones and the 9 pin-file tests (§3.1). Nothing
  else failed; the intermittent `...reservation_released[untriggered]` passed this run. The one
  warning is the pre-existing starlette `BlockingPortal` deprecation, as in round 1;
- round 2's draft freeze (scratch) through the committed `prep/freeze_compare.py`: 30 `functions`
  and 22 `files` entries, 0 differ from Phase 19's `3636ca21…`; only `algorithm_hash`,
  `runtime_hash` and `tree_lab` move; `assess_pairs` `783e8e58…`, `scorer_hash` `19de811c…`,
  `completion.md` `e3b9362f…` (exit 0);
- `prep/v1_function_hashes.py`: all four v1 functions and six constants unchanged since `f4014f0`;
  `prep/phase18_reassessment.py`: HARM / `check_failure`, equal to the stored assessment (both
  exit 0);
- both runners' dry plans on the real repository exit 0 and create nothing; with every pin filled
  in a scratch shadow, both show every pin `MATCH` and the two runner test files give 250 passed,
  0 skipped;
- the mutation check (`prep/round2-mutation/`): every round-2 guard of the generator and the
  backend guard's M3/M5 are killed; of the runners' 13 mutants, 11 are killed and 2 are equivalent
  (above);
- the backup-branch commit and the seal checks were rehearsed in a scratch clone; the real
  repository's backup branch is still at `2c62d0e`.

**Still open after round 2 (none is the fixer's to decide):** the v2 decision (§6.8), recorded by
the approver; R4, R8 and R9 recorded by the approver at F1 (round 2's statistics lens confirms R4
and R8 and recommends keeping $87); then the freeze, the pins, the seal and the approvals (§7.4,
§8).

### Approver decisions (2026-09-24; Claude as PM, delegated by project owner Shree Bohara)

**v2: adopted (§6.8).** The declared criterion is **not met literally**. Its power half fails on
3, 1 or 2 of 5 cases depending on the reading (§6.5), and in substance in all three. That is
recorded here plainly, not re-declared. Adopted anyway, for these reasons, each from §6.4–6.7:
- **The committed reading (b) fails only the transient-upgrade case**, and the program
  anticipated that case in advance ("No design with 15 trials or fewer fixes that, and it is
  stated"). There, neither design can see a loss: v1's power (0.21) barely exceeds its own
  false-alarm rate (0.17).
- **v2 removes the defect that undermined Phase 18.** Rule 3's per-case false HARM falls from
  up to 34.4% to at most 4.1%.
- **It cuts false NO_HARM against a real halving** from 0.09 to 0.01.
- **Its main cost is fewer verdicts per attempt**, driven by the lapse on the
  delayed-confirmation case. That cost becomes "no verdict" (INCOMPLETE), never a wrong
  verdict. For a safety check, fewer wrong answers outweighs fewer answers.
- **At the non-defect rule-1 pool** (the fixed lab: the pool's only event was Phase 19's drift),
  P(NO_HARM | a verdict) for a harmless policy is 0.90 against v1's 0.75.
- **What every Phase 24 verdict must state** (§6.6):
  - the transient-upgrade floor;
  - the small-loss blind spot on high-rate cases (item 9);
  - the verdict-rate cost (item 6);
  - the delayed-confirmation INCOMPLETE-only harm (item 10).

**R4, R8, R9:** confirmed as round 2 recommended.
- *k* is 1-based.
- "New" includes T15's `ec1acaf7…`.
- The cap stays **$87**: 1 attempt guaranteed, usually 2, and a 3rd if the first two charge
  ≤ $34.83.

**N3: decided (a), overriding round 2's (b).** Phase 21 is closed, and its harness correctly
refuses on any later configuration.
- **The change:** the 17 configuration-dependent tests in `test_lapse_probe.py` now carry a
  declared skip marker, applied only when the tree's configuration hash is not Phase 21's
  `0a33aa51…`, with the reason stated. This is the same pattern as `test_run_dev_probe.py`'s
  `frozen_only`.
- **Why:** a permanently red suite hides new failures. Keeping 17 accepted failures by id is
  brittle.
- **Scope:** the change is test-only. `lapse_probe.py` (the pinned harness, `f701ba14…`) is
  unchanged, and the Phase 21 results are unaffected. The test file's pre-change copy is kept
  in the session scratchpad and backed up.
- **F2's expected full-suite output is therefore:** 0 failures or errors from
  `test_lapse_probe.py` (20 skips there), the 30 `test_run_dev_probe.py` skips, and the 9
  pin-file skips.

