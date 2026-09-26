# Phase 28 protocol — the full loop on the upgrade-side source: 50 attempts, one futility look

**Status: declared before any paid call; reviewed in rounds 1–3 plus a focused check of round 3's fixes; landed and
frozen on 2026-09-26; approved by Claude (Opus 5.5) as PM, delegated by the project owner.** No paid, model,
provider or W&B call had been made for this phase at approval. The code was built on 2026-09-25 in a detached
worktree of `backup/part2-2026-09-22` (`3cda105`) and landed in the main checkout at §9 F0 on 2026-09-26. Every
number below is a $0 measurement on that build or is carried from `PHASE28_DESIGN.md`, and its source is named.
Review rounds 1 (three lenses, 17 findings), 2 (two reviewers, 12 findings) and 3 (two reviewers, 7 findings) all
returned RUN_WITH_CHANGES, and every finding is applied; round 3's code fixes were reviewed by an independent focused
check that found no new defect (Review log, "Closure of round 3"). P0 preserved the last closed round, and §9's F0–F9
are done; the approval record is `artifacts/phase28-2026-09-26/review.json` (F10).

Reviewed for launch: harness d8689fcfae7a79d028a9021d8863172daf5788572d1dca82cb0e0ca9d2d2d146 plan 0779572d3c609078efb8009d41519e6abd45025cd4768b07859a7048caca1c07

- **Program:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`, Phase 28 (cap about $100–150).
- **Design (read first):** `docs/part2/PHASE28_DESIGN.md`, revised after design review round 1; the approver took
  all seven recommendations (§19 there). **Phase 29 is cancelled**, so only Phase 30 must end before the backend
  change lands.
- **Precondition:** Phase 28a (`PHASE28A_EXPERIMENT.md`) returned **GO**. On a NO_GO or an unapproved INCOMPLETE,
  this phase closes with the probe as its result and nothing below is landed. The runner checks it on disk (§10
  item 6), and so does the landing check (§9 F0). The build existing already (§2 row 9) has no bearing on it.
  **Met:** Phase 28a ended on 2026-09-26 (UTC) with GO, 13 of 30 first proposals re-sending the upgrade
  (`PHASE28A_RESULTS.md`). Its run is `artifacts/phase28a-2026-09-25/live`: the manifest is COMPLETED, and it wrote
  its own `readouts.json` (sha256 `1c72dc35c0a6b0654714b369bb6099cff7be29270ebc0cf967c6e46e131c8a8c`), which is
  therefore the file the review record must name (§9 F10); the fallback of §10 item 6 does not apply.
- **Runner:** `scripts/experiments/run_upgrade_loop.py` (new). **Tests:** `backend/tests/experiments/test_run_upgrade_loop.py`.
- **Backend change:** `backend/app/lab/completion_study.py` and `backend/app/lab/api.py`. **Tests:**
  `backend/tests/lab/test_completion_manifests.py`. One declared test skip in `backend/tests/experiments/test_run_gap_probe.py` (§3.3).
- **Imported, never edited:** `run_full_loop.py` (`07dcaa93…`), `run_full_loop_fixed_n.py` (`95ef698d…`) and
  `slot2_probe.py` (`28b998ac…`, its paid-run process guard only).
- **Evidence folder:** `artifacts/phase28-<date>/`, where **`<date>` is the landing date** (the day F0 runs), used
  for every step after it and for the run's `--out`, even if the run starts on a later day (review round 2, LN-4).
  It holds `prep/` (§9). Until F0 the prep scripts and their outputs are in the scratch folder `p30-28/p28-final/prep/`
  (the round-3 fixes), and P0 copies them, with the build and the evidence of every round, to
  `artifacts/builds/phase28-2026-09-25-r<N>/` for the last closed round N.
- **The owner's direction, as context only:** "go ahead with whatever u recommend" (Shree Bohara, 2026-09-25,
  relayed by the workflow harness). It covers the direction of Phases 28–31. It is not this phase's approval,
  which is recorded in the review record (§10) after the review closes.

## 1. The question

On the fixed lab, with the byte-identical Mechanic brief (`completion.md`, `e3b9362f…`), the v4 Actor context and
the Phase 17 settings, with the completion study's source case moved to an **upgrade-side transient failure**
(`upgrade-3`: F4 on `update_order`, 3 failures):
- **How often does a fresh full study produce a completion repair that passes Phase 17's certification rule,
  transposed to that source?**
- **Do the repairs it certifies re-send the upgrade, and does the re-send fire?**

Not asked: held-out safety (none can follow, §13); whether one repair closes both gaps; whether a certified
policy's notification-side rules are safe (no case here can run them); ACCEPTED (a completion study cannot
write it, Phase 16; the promotion path has no known source, Phase 20).

## 2. Where this protocol departs from the design or from the build brief

| # | design (`PHASE28_DESIGN.md`) | as built and declared here | why |
|---|---|---|---|
| 1 | §8.1 item 3: `source_clause` returns NO_CHANGE only when `assess_pairs` returned OBSERVED_IMPROVEMENT. §5 and §8.2 claim the result then equals `assess_pairs` with the literal replaced in **decision and reason** | `source_clause` replays `assess_pairs`' per-case loop from `by_case`, in manifest order, whenever the stored reason came from that loop or after it (regression, no gain, gain). A regression on an earlier case still wins; the source clause wins over a later regression or a missing gain, exactly as the replaced literal would | the design's literal code gave the same **decision** in all 4,096 combinations of the property test but a different **reason** in 473 (e.g. "Expected outcome regressed" where Phase 17's gate says "Healthy or source completion was not preserved"). The built version matches both in all 4,096, and the property test checks both. Saved: `p28-build/explore/design_clause_vs_reference.out.txt` |
| 2 | §8.1 item 4: `build_case_manifest(case_manifest_id or DEFAULT_CASE_MANIFEST)` | `DEFAULT_CASE_MANIFEST if case_manifest_id is None else case_manifest_id`: an empty string is refused as unknown, before any state | with `or`, `''` would run the default manifest while `record['case_manifest_id'] = ''` made every later `check()` refuse after state was taken |
| 3 | §8.1 item 1 | the builder also refuses when `load_manifest('development')`'s hash differs from `case_manifest()`'s `source_manifest_hash` | a defensive check; it never fires on an unchanged tree |
| 4 | §8.3 pins; §4.2(d) "the new functions" (4 named) | the supplementary hashes are one pin, `DECLARED_FUNCTION_HASHES`: text and AST sha of **7** definitions, the 4 the design names and the 3 module constants they read (`DEFAULT_CASE_MANIFEST`, `SOURCE_CLAUSE_OUTCOMES`, `SOURCE_CLAUSE_REOPENS`). All are taken with the venv's Python 3.12.8. The launcher sha is a checked file pin. At launch the runner also recomputes the backend builder's manifest hash and refuses on a difference, and the review record must name a final Phase 28a run that said GO (§10 item 6) | the design lists these values; this states how they are checked. The 3 constants and the 28a check were added in review round 1 (Review log BK-3, IN-3, IN-4) |
| 5 | §8.3 | the run record is `artifacts/phase28-<date>/upgrade-loop-manifest.json` | a name distinct from Phase 23's; `slot2_probe`'s other-run glob (`phase2[6-9]-*/*manifest*.json`) still sees it |
| 6 | §8.3 tests "on real stored event shapes" | three stored episodes are pinned as excerpts (type, `call_id`, payload without attempt ids) and tested; a second test re-reads the stores and compares, and skips where the stores are absent (a worktree) | the predicates are tested everywhere; the excerpts were checked equal to the main checkout's stores on 2026-09-25 (read-only) |
| 7 | §8.2 "with a fake runner through `_execute`" | the real runner and the in-process simulator run an `upgrade-v1` study end to end with fixture providers; the clause case re-labels one validation L trial of `upgrade-3` after it runs, as `test_completion_study.py`'s untriggered test does | it tests the real path, including `check()` at every slot, at no cost (12 s per study) |
| 8 | §8.2 fallout "found now: four files" | measured on an overlay of the built code with cloned artifacts: **one** test fails instead of skipping (§3.3); the rest move from passed to skipped under their existing guards. Phase 28a's test file was written after those overlays ran; its guard covers it (§3.3) | measured, not assumed; the 28a file by its guard's code and store-free overlays |
| 9 | §9 step 2 and §18: the backend change is built **only after a 28a GO**, and "never built" on a NO_GO | the change was built on 2026-09-25 **before** Phase 28a ran, in a detached worktree. No money was spent, and nothing on the main checkout was edited. **Landing and running are still gated on a 28a GO:** step F0's landing check and the runner's review-record check (§10 item 6) both refuse without a final 28a run whose read-outs say GO. On a 28a NO_GO the build is discarded, never landed | building early costs nothing, but it is the sunk-cost pressure the design's order was meant to keep away from 28a. So, declared: **the existence of this build has no bearing on Phase 28a's review, its decision or any approval of a 28a re-launch or completion** (Review log IN-3) |
| 10 | §7.2 S2u(ii): "qualified ÷ all step candidates" | "qualified ÷ step candidates **tested at the source gate**", which is Phase 17's S2(ii) wording (`PHASE17_EXPERIMENT.md`: "all step candidates tested"). A within-study duplicate, which never gets source trials, and a step candidate whose study ended before its source gate are in neither denominator, and each is reported on its own | the design dropped the word "tested", and a slot-2 duplicate would have deflated the rate (Review log RN-6). Declared before any data exists |

| 11 | §9 F3 "Review rounds (§11). After any fix, back to F2", after landing; §11 "at least two adversarial rounds before F4" | **every review round, its fixes, its Review-log entry and its closure happen in the worktree, before F0** (§9, "the one rule"). No review round runs after landing. A finding after F0 that needs any change to a build file (a declared skip or a protocol edit included, the F7 and F9 fills excepted) rolls the landing back and restarts at F0 with a new, reviewed round | rounds 1 to 3 ran in the worktree before landing, as they must: a fix made on the main checkout after landing would be unreviewed code in the tree that F4 freezes. The design's order left open how a round is recorded relative to landing (review round 2, LN-2) |

Nothing in the certification rule, the case set, N, the cap, the look, the stops or the read-outs departs from the
design, apart from row 10's denominator.

## 3. What is fixed, and what changes

### 3.1 Unchanged, and pinned as unchanged

- `assess_pairs` text `783e8e58…` at lines 106–147; `case_manifest` `0a5346c8…` at 43–83 (its output still
  `7ab9368e…`); `planned_slots` `495f60fc…` at 86–103. All new code is appended after `_execute`, so these keep
  their text **and** line ranges (re-checked by `test_completion_manifests.py` and by the runner at launch).
- `MODEL_CALL_RESERVATION` 484, `PROPOSAL_SLOTS` 2, the evidence constants, the source-gate call.
- `scorer_hash` `19de811c…`; `checks.py` never opened; `completion.md` `e3b9362f…`; the settings file
  `1e2002d3…`; `heldout_check.py` and the four v1 held-out functions; everything under `backend/app` except the
  two files below.
- Every earlier-phase harness and runner (`slot2_probe.py`, `report_word_probe.py`, `lapse_probe.py`,
  `run_gap_probe.py`, `run_full_loop*.py`, `run_dev_probe.py`, `run_heldout*.py`), `gate_freeze.py`,
  `check_clock_drift.py` and `check_ingestion_health.py`.

### 3.2 The backend change (build items B1, B2)

`backend/app/lab/completion_study.py`:
- `queue_completion_study(..., case_manifest_id=None)`: the manifest is `build_case_manifest(id)`, before the
  lock, so an unknown id is refused before any state; a replay with a non-default id is refused; the record gets
  `case_manifest_id` **only** when a request names one, so a default request writes exactly today's record.
- `_execute`: `check()` rebuilds the manifest from the recorded id; the source and control come from the
  manifest's `source_case_id` and `control_case_id` (for `notification-v1` the same two cases as before); both
  validation calls become `source_clause(assess_pairs(...), record['manifest'])`. The candidate-marking code is
  unchanged, so a clause rejection marks the candidate REJECTED, as Phase 17's gate would.
- Appended after `_execute`: `upgrade_case_manifest()`, the closed registry `CASE_MANIFESTS` /
  `DEFAULT_CASE_MANIFEST = 'notification-v1'`, `build_case_manifest()` (refuses unknown ids and any manifest whose
  control is not the literal `healthy`), and `source_clause()` (§2 row 1).

`backend/app/lab/api.py`: `CompletionStudyRequest.case_manifest_id: str | None` (max 40); the route passes it.
Unknown fields stay forbidden (422).

### 3.3 Declared test skips for tests pinned to configuration `2cf63e93…` (build item B4)

Measured on 2026-09-25 by running `backend/tests/experiments` (and the full suite, §3.5) on two overlays with
cloned artifacts: one with the Phase 22 backend (its gate freeze equals `8994e962…` byte for byte) and one with
this build.
- **Fails instead of skipping (declared skip added):** `test_run_gap_probe.py::
  test_the_phase17_settings_reproduce_the_phase22_configuration_hash_without_env`. It recomputes the
  configuration from the code on disk and asserts `2cf63e93…`. The skip uses the `NEEDS_PHASE21_TREE` pattern of
  `test_lapse_probe.py` (`NEEDS_PHASE22_TREE`, applied at the end of the module) and keys on the whole Phase 22
  freeze (`tree_is_phase22_frozen()`), **never on the asserted hash**, so on the Phase 22 tree the test still runs
  and passes (checked). The harness `run_gap_probe.py` is not edited.
- **Move from passed to skipped under their existing guards (no change):** `test_report_word_probe.py` 14,
  `test_report_narrow_probe.py` 8, `test_slot2_hidden_probe.py` 16, `test_slot2_probe.py` 18,
  `test_run_gap_probe.py` 42.
- **Phase 28a's tests, not in the overlays above (corrected in review round 1):**
  `backend/tests/experiments/test_upgrade_mechanic_probe.py`, for the harness `scripts/experiments/upgrade_mechanic_probe.py`.
  - Both files were written on the main checkout at 14:39–14:40 on 2026-09-25, after the builder's overlay runs
    ended (14:30). So neither overlay held them, and the full-suite comparison below does not cover them. (An
    earlier version of this protocol named the file `test_mechanic_upgrade_probe.py`, the design's name. That was
    wrong.)
  - **Expected (restated in review round 2, LN-6): every store- or configuration-guarded test in the file skips,
    and none fails.** No count is declared, because the file kept changing while Phase 28a was reviewed (it changed
    again at 16:04, 16:09 and 17:02 on 2026-09-25). Its store and configuration tests are guarded by
    `_tree_is_the_declared_configuration()` (the `needs_store` mark and the `real` fixture), which recomputes the
    configuration from the code on disk and skips unless it is `2cf63e93…`, so on the moved tree they skip rather
    than fail. No declared skip is needed.
  - Measured on store-free overlays of the main checkout, with and without this build: 38 passed, 29 skipped and 0
    failed on both (round-1 reviewers, `r28-backend-review/tests-28a-ov-base.txt` and `-changed.txt`); 46 passed, 31
    skipped, 0 failed on both after the 17:02 change (round-2 reviewer, `p28-adv2-whatbroke/tests-28a-ov-*.txt`); and
    the round-2 fixer's own run on the final build (Review log, round 2). Store-free overlays show that no unguarded
    test fails; they cannot show the store-backed tests skipping for the configuration.
  - **F2 on the main checkout after landing is the measurement that counts**, and the file is in F2's targeted list.
- **A new declared skip is a build change (review round 2, LN-6).** If F2 finds any test that fails instead of
  skipping, in any file, its declared skip is made in the worktree, not on the main checkout: the file joins the build
  (§9's build files, the landing check's `REVIEWED` and `BASE`, the preserve and F11's list), the round's reviewers
  read it, and the steps restart at F0 after rolling the landing back (§9, "the one rule"). The pinned harnesses are
  never edited.
- **Fail on both trees, not caused by this change (reported, not touched):**
  `test_run_dev_probe.py::test_the_real_store_holds_both_policies_unchanged` ("found 2" policies with the declared
  L hash in the current store) and `test_slot2_hidden_probe.py::test_the_owners_answer_gate_on_the_real_protocol_text`
  (Phase 29's protocol now ends with its Cancellation section).
- **The full suite on both overlays** (2026-09-25): Phase 22 backend 4 failed, 1,703 passed, 50 skipped; this
  build 3 failed, 1,717 passed, 149 skipped. Per test, the only differences are the 112 new tests (all pass),
  the 98 guarded skips above (one of them a `test_slot2_hidden_probe.py` stop-handler test that failed on the
  Phase 22 overlay with a stray `Detached` signal) and the one declared skip. The
  third failure on both, `tests/integration/test_foundation.py::test_all_process_bindings_are_local`, is an
  overlay artefact (the overlays have no `frontend/`). These overlays predate Phase 28a's test file (above), and
  the round-1 fixes add 27 tests in the worktree (§3.5). F2 re-runs everything on the main checkout after landing.

### 3.4 What moves in the gate freeze (measured on the build, 2026-09-25)

`gate_freeze.py --root <worktree>` against Phase 22's freeze (`8994e962…`), checked by `prep/freeze_compare_p28.py`
(exit 0; on the unchanged tree it exits 1, the negative control). **Exactly** these entries differ:

| entry | Phase 22 | this build (preview; re-taken at F4 on the main checkout) |
|---|---|---|
| `files: backend/app/lab/completion_study.py` | `c3fc2234…` | `03e3d8be…` |
| `functions: completion_study.py::queue_completion_study` | `fe3bcae1…`, lines 150–211 | `e6d34aec…`, lines 150–222 |
| `functions: completion_study.py::_execute` | `07b58b8e…`, lines 214–474 | `1f0a4bf6…`, lines 225–485 |
| `fingerprints: tree_lab` | `e3050c56…` | `f4305dbc…` |
| `fingerprints: algorithm_hash` | `f2f71c59…` | `88eb5b77…` |
| `fingerprints: runtime_hash` | `67e6d968…` | `18332ec3…` |

Every other function, file and fingerprint entry is byte-equal as a whole, including `lines`. `api.py` has no
entry of its own; it moves only `tree_lab`, `algorithm_hash` and `runtime_hash`. The configuration hash therefore
leaves `2cf63e93…`: through Phase 22's no-`.env` script on the build it is `96a30c69…` (preview only; F5 takes the
pin, with `algorithm_hash` and `runtime_hash` equal to the table above).

These six values are also the **reviewed values**: since review round 1, F4's compare refuses a freeze whose six
moved entries differ from them, however they moved (§9 F4). They come from the worktree's gate freeze (sha256
`bb0b19a9…`), which the round-1 backend reviewer regenerated independently.

Supplementary hashes of the new definitions (`prep/new_function_hashes.py`, preview; F4 records the pins). Review
round 1 added the three module constants that `build_case_manifest` and `source_clause` read, because a change to
`SOURCE_CLAUSE_REOPENS` alone turns the clause into a pass-through on one path while `source_clause`'s own hashes
stay the same (tested). **An AST sha depends on the Python version**: Python 3.9.6 gives different AST shas for the
three functions. So the values below are taken with the venv's Python 3.12.8, the script records the interpreter
and refuses under any other, and F4 refuses a record taken under another:

| definition | text sha256 | AST sha256 (Python 3.12.8) |
|---|---|---|
| `upgrade_case_manifest` | `db52a805…` | `fd77006c…` |
| `CASE_MANIFESTS` (the assignment) | `196327a2…` | `c1a3248a…` |
| `DEFAULT_CASE_MANIFEST` (the assignment) | `5adef5e2…` | `a064c48e…` |
| `build_case_manifest` | `3220e7e9…` | `c5df4b79…` |
| `SOURCE_CLAUSE_OUTCOMES` (the assignment) | `fb2a8d36…` | `2755d2b9…` |
| `SOURCE_CLAUSE_REOPENS` (the assignment) | `55579614…` | `74874e9a…` |
| `source_clause` | `4f3468cd…` | `51d5b4c3…` |

### 3.5 Tests of the build

- In the worktree (no `artifacts/`): the new and changed files pass, and the full suite result is in the build
  report of 2026-09-25 with every failure and skip listed. Tests that need the stores or the Phase 22 freeze skip
  there by design. After each round's fixes, see that round's test record in the Review log.
- On the overlays: see §3.3. The intermittent `[untriggered]` failure (pitfall 85) is reported whenever it appears;
  the suite is never called unconditionally green.

## 4. The case manifest `upgrade-v1` (declared; `PHASE28_DESIGN.md` §4)

| # | case_id | fault_spec (seed) | expected | role |
|---|---|---|---|---|
| 1 | `healthy` | none (101) | COMPLETED | control; `assess_pairs` demands L 3 of 3 |
| 2 | `upgrade-3` | F4 `update_order`/`orders`, occurrence 1, `failure_count` 3 (703) | COMPLETED | **source**: controls, source gate, validation; `source_clause` demands L 3 of 3 |
| 3 | `upgrade-2` | F4, `failure_count` 2 (702) | COMPLETED | fresh sibling; the only case that can supply condition 3 |
| 4 | `delayed-upgrade` | `dev-3`: F2 `update_order`, SUCCEEDED after 3 ticks (103) | COMPLETED | guard: a delayed success |
| 5 | `upgrade-18` | F4, `failure_count` 18 (718) | SAFE_UNRESOLVED | guard: the repair's own re-send fails again |
| 6 | `lost-upgrade-response` | `dev-2`: F1 `update_order`, 1,500 ms (102) | COMPLETED | guard; gated rules cannot run here |
| 7 | `terminal-upgrade-rejection` | `dev-5` (105) | CORRECTLY_REJECTED | refusal guard |

`healthy` and `terminal-upgrade-rejection` are copied from `case_manifest()` and are byte-identical to
`7ab9368e…`'s. Manifest fields: `source_case_id 'upgrade-3'`, `control_case_id 'healthy'`, `repeats 3`,
`validation_feedback_forbidden true`, `ordinary_policy_accepted false`. 7 cases, so 60 slots and the frozen 484-call
reservation hold (tested).

**Hash (measured, a preview until F6 pins it):** the backend builder gives
`cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3`, equal to the stdlib mirror
(`prep/draft_manifest_r1.py`, which first reproduces `7ab9368e…` by the same method) and to the design's value.
The builder's `upgrade-3` fault spec is printed by `prep/manifest_hash.py`; F6 compares it with the spec Phase 28a
sent.

## 5. The certification rule (Phase 17's, transposed; never loosened)

An attempt is **CERTIFIED** only if all hold:
1. **Identity.** A full, non-replay completion study; Actor context `faultlab-actor-context/v4-indexed-evidence`;
   evidence `faultlab-compact-evidence/v2-task-outcome`; `case_manifest_id == 'upgrade-v1'` and `manifest_hash`
   equal to the pin, at start and after finishing; the post-finish checks (identity, evidence project, backend
   process) passed.
2. **The transposed gate.** The study decision **and** its validation assessment are OBSERVED_IMPROVEMENT, from
   the unchanged `assess_pairs` followed by `source_clause`.
3. **Fresh gain.** On at least one validation case other than `upgrade-3` and `healthy`, L completed − B0
   completed ≥ 2, per case, never summed (pitfall 73).
4. **The source clause, re-checked by the runner.** In validation the candidate completed `upgrade-3` 3 of 3. A
   stored OBSERVED_IMPROVEMENT that fails this is an **integrity failure**: the row is never certified and the run
   aborts.

Condition 3 is all but implied by condition 4 for a one-re-send policy (`upgrade-2` and `upgrade-3` behave the
same from the policy's side); what it adds is that the baseline completed `upgrade-2` at most 1 of 3. It is kept
because it is Phase 17's rule. **It is not evidence of generalisation.** Nothing is called ACCEPTED, no pointer
moves, nothing is activated.

## 6. Design

### 6.1 Attempts

**N = 50, fixed in advance** (`N_ATTEMPTS`). A certified study never stops the run. Every attempt is in the
denominator, including $0 runner refusals and a stop during campaign create (labelled as in Phase 23).

### 6.2 Stop rules (the only ones)

| stop | when | final? |
|---|---|---|
| `futility` | the look (below) fires | **final**; "Stopped for futility at n = j" |
| `fixed_n` | 50 attempts recorded | **final** |
| `spend_guard` | no study starts once charged + $11 > $150 | **final**; "Truncated at n = j" |
| `breaker` | 5 consecutive infrastructure failures (runner-side rows skipped, as in Phase 23) | no; resumes only with the user's approval |
| `aborted` | Ctrl-C, SIGTERM, SIGHUP, a failed pin or check, another paid run appearing, an integrity failure (§5 condition 4), or any other error inside the main loop (a print into a closed pipe, say: output inside the loop uses `print`) | no; resumes only with the user's approval |

**An integrity failure is always the recorded abort (review round 1).** Inside the main loop it aborts at once. When
`recover()` finds one after another stop, it becomes the recorded abort too:
- **in the sweep after an abort** (say lost contact while the study ran): the stop is `aborted`, and `abort_detail`
  names the integrity failure first and the earlier cause after it;
- **on resume** (say after a signal left the study running): the resume that finds it records it as the abort and
  **refuses**, before any new campaign.
- The next `--resume --after-abort` is then an approval given with the failure in view, and it continues. The row
  stays not certified.
- The rule: an integrity failure on record that no recorded stop names yet is recorded as the abort before anything
  else happens.

### 6.3 The futility look

- **When.** At the top of the main loop, before any other stop check and before attempt n+1 starts, over rows
  1..n (including rows recovered on resume), the first time **D ≥ 16** holds and no look record exists.
- **D** = distinct policy hashes, across the run and any slot, of candidates that became a valid policy
  (within-study duplicates, refusals, `no_change` answers and invalid outputs excluded). **R** = how many of those
  contain `retry_original_request` with `service: orders`, at any hook, under any `only_if` (present, not
  working). **k** = certified rows so far.
- **Stop** if R = 0 and k = 0; otherwise the look **passed** and is never repeated. Precedence: the look, then
  `fixed_n`, then `spend_guard`. Both precedences are tested: a look that fires at n = N stops for futility, and so
  does one that fires on the iteration where the spend guard would also trip (review round 1).
- **D counts any slot**: a valid slot-2 policy counts as a slot-1 policy does (tested with D reached only through
  slot 2, review round 1).
- **Recorded** as `futility_look = {attempt, D, R, k, outcome, evaluated_at}` in the run record. For a stop, the
  record and `stop_reason = 'futility'` are written in the **same save** (tested on every save).
- **A futility stop stays final even if its write-up is interrupted (review rounds 1 and 2).**
  - A signal, Ctrl-C or error after the look's save and before the loop ends (a print into a closed pipe, say)
    leaves the stop `futility`. The interruption is kept in the session record
    (`interrupted_after_the_futility_stop`), never written as `aborted`, and the session's write-up completes.
  - **Output after the main loop cannot end it early (review round 2, WB-1).** The abort handlers and the write-up
    print through `say()`, which drops a write error (a closed pipe, a lost terminal): the run record on disk is the
    result, and the console only a copy. Round 1's handler printed with `print()`, so a closed pipe re-raised
    `BrokenPipeError` out of `main()` before the summary or the end time was written (the stop itself was already on
    disk) and without keeping the interruption, so the sentence above was false for its own example. Tested with
    every print after the look raising.
  - If the process dies before the session's last save, the stop is still on disk. The next resume refuses (the
    stop is final), but it first writes the end fields from the rows on record, with no new work. **Which fields is
    decided by the last session, the one that ran the look (review round 2, WB-1):** if that session has no
    `ended_at`, the budget total is read again over every campaign on record, the summary is recomputed with it,
    `ended_at` (the run's and the session's) is set to the look's own evaluation time, and `clock_drift` is marked
    skipped in the run record and the session record, so the drift check is run by hand (§11 step 8). Values an
    earlier session of a resumed run left in the run record are never kept; each earlier session keeps its own drift
    result in its session record. Nothing runs after the look, so reconcile's window then closes where the run's own
    studies ended, and a foreign study started during that session is still inside it (tested). Every field
    written is named in the refusal and in the run record's `futility_write_ups`. Round 1 decided by whether a key
    existed, so on a resumed run it kept session 1's total, end time and drift result (review round 2's probe: $10
    recorded against $32 spent, and a foreign study from session 2 missed).
  - **Until that resume has run, reconcile does not trust the record (review round 3, R3-1).** Before it, the end
    time, total, summary and drift result are missing or an earlier session's, so reconcile's window would close at
    session 1's end and miss a foreign study started during the last session (round 3's probe: 0 discrepancies and 0
    untracked studies on such a record, at four points of death). Reconcile therefore reports any final stop whose
    last session has no `ended_at` as a discrepancy, and says to run the resume command once and then reconcile
    again (tested at three points of death). The runbook runs that resume when the runner died after a final stop
    (§11 step 7).
- **On resume.** If D ≥ 16 and no record exists (an abort between the crossing attempt and the evaluation), the
  look is evaluated before any new attempt (tested: no new campaign starts). A `passed` record is never
  re-evaluated. A `stop` record is final; if a crash left the stop reason or the session's end fields unwritten
  (above), the runner writes them and refuses to continue. `FUTILITY_LOOK_D`, the look's rule text and its
  precedence are in the plan, so a resume with a different look is refused.
- **Reconcile checks the look exists (review round 1).** Once the rows reach D ≥ 16 at attempt j, a run that went
  past j, or ended final, must hold a look record with `attempt == j`. A run stopped early at exactly j may not
  have one yet, because resume evaluates it first.
- It can fire only when nothing is certified and the Mechanic has never written the step, so it cannot truncate a
  success. What it reports: "0 of D distinct Mechanic policies shown upgrade-side evidence re-sent the upgrade
  (Wilson upper bound 19% at D = 16)".

### 6.4 Continuation after an early stop

Only `--resume --after-abort` on the same `--out`, with the user's approval. Refused on any changed plan, harness,
protocol or review record (`declared = {plan, plan_hash, harness_sha256, protocol_sha256, review_record_sha256}`),
on any code or settings difference from the freeze, and on any reconcile discrepancy or untracked study. A second
`phase28-*` folder is refused. `fixed_n`, `futility` and `spend_guard` are never resumed or topped up: no attempt
runs after them. One exception to "never resumed" is only a write-up (review round 3, R3-1): after a futility stop
whose session died before its end save, the resume command is run once. It refuses the final stop, and before
refusing it writes the missing end fields from the rows on record (§6.3). It needs no approval, and it starts
nothing.

## 7. Declared read-outs

All are computed by the runner from its attempt rows and the `events` table (pitfall 50), saved in the run
record's `summary`, and never re-declared after data exists.

### 7.1 Primary

**k of n attempts produced a certified upgrade-side completion repair, with a Wilson 95% interval.** Pre-fixed
wording (in `primary_statement`):
- `fixed_n`: "*k* of 50 attempts produced a certified upgrade-side completion repair (Wilson 95% [*lo*, *hi*])."
- `futility`: "Stopped for futility at n = *j*: 0 of *D* distinct Mechanic policies re-sent the upgrade; 0 of *j*
  attempts produced a certified upgrade-side completion repair (Wilson 95% [0, *hi*])."
- `spend_guard`: "Truncated at n=*j* by the $150 spend guard: …". `breaker` and `aborted`: "Stopped at n=*j* …
  This is not a finding about the loop."
- **Every form ends with the scope sentence:** "Development cases only; no held-out check can follow. The
  validation set has no notification-fault case, so a certified policy's notification-side rules were never
  exercised; lost-upgrade-response cannot exercise a gated rule."

Never quoted without the funnel (§7.2), S4 (§7.5), the distinct certified policies (§7.3), the guard table (§7.4),
the cumulative count (§7.6) and the Phase 28a result.

### 7.2 The funnel (`summary.funnel`, and per attempt in each row's `funnel`)

- controls stops, **split by cause** (source leak, healthy lapse, too few valid controls); infrastructure deaths
  (runner-side rows excluded); first proposals drawn (a refusal or invalid output is a draw without the step).
- **S1u:** first proposals with an orders re-send ÷ first proposals drawn; also **R of D**.
- **How each re-send is written:** hook, `when`, `only_if`, the number of orders re-send steps, and a static label
  ("cannot fire after a transient failure" when gated on `current_operation_pending`, pitfall 77; "can fire";
  "unclear").
- **Fires:** in at least one source-gate L trial the policy itself dispatched `update_order` (a `tool_dispatched`
  event with `caller: policy`, `tool: update_order`); present but never fired; validation trials in which it fired.
- **S2u** (Phase 17's S2, transposed; §2 row 10): (i) qualified ÷ step candidates with complete pairs; (ii)
  qualified ÷ step candidates **tested at the source gate**. A within-study duplicate (the same policy again, which
  gets no source trials) and a step candidate whose study ended before its source gate are in neither denominator.
  Each is reported on its own: `upgrade_retry_within_study_duplicates` and `upgrade_retry_never_tested_at_source`.
  "Step candidates" (`upgrade_retry_present`) excludes the duplicates. Qualified without the step is reported
  separately. **Source-gate leaks:** a source-gate NO_CHANGE with ≥ 1 B0 completion.
- **Validation:** reached; assessed; clean and dirty; accepted on clean ÷ clean; accepted on dirty is 0 by
  construction and labelled so (pitfall 72).
- **Rejection reasons, with the case** (replayed in the gate's order): refusal, `delayed-upgrade`, `upgrade-18`,
  `lost-upgrade-response`, `healthy`, a candidate check failure, or the **transposed source clause**, worded
  "Phase 17's gate would also have returned NO_CHANGE: the candidate completed the source fewer than 3 of 3".
- **OBSERVED_IMPROVEMENT, not certified:** each study listed as "store says OBSERVED_IMPROVEMENT; not certified (no
  fresh gain)". **Integrity failures:** expected 0; any one aborts the run.

### 7.3 Distinct hashes (pitfall 29)

Draws; distinct policies; distinct first proposals; distinct with the upgrade re-send; within-study duplicates;
re-draws across attempts; certified in order; distinct certified policies; whether each certified hash existed in
the store before the run (a read-only query at report time); both-sides policies (an orders re-send and the Phase 9
notification step); any re-draw of `dd62c857…`, `711bddb6…`, `5735a918…` or `d4bc993e…`.

### 7.4 Which guards did a repair's rules actually run on?

For every validation-reaching candidate, by case: L and B0 counts; L trials with an executed `policy_step`
(pitfall 79); L trials where the policy dispatched `update_order`. A guard where no rule ran in any L trial is
labelled **"not exercised"** for that candidate. For a certified repair "keeps" is guaranteed by the gate; the
informative figure is how many source-qualified repairs were rejected in validation, and on which guard (§7.2).

### 7.5 The nuisance, quoted beside every validation result (S4)

Untriggered faults per fault-bearing episode, all stages, LAB_ERROR excluded, with a Wilson interval. Every fault
here is upgrade-side; the notification-fault episode count is reported and is 0 by design. Not comparable with
Phase 17's 0.65% or Phase 23's 1.6%.

### 7.6 Secondary: the cumulative count (Phase 17's pooling rule)

"*k* + 4 certified completion repairs in *n* + 39 attempts across Phases 17, 23 and 28", always with: "Phases 17
and 23 used the notification source and Phase 28 the upgrade source, so this is a count required by Phase 17's rule,
not a rate." No pooled share is quoted (`rate: null`).

### 7.7 Also reported

- **The baseline's leak on `upgrade-3`:** B0 completions ÷ valid B0 trials, controls and source gates pooled; and
  the episodes where the Actor itself re-sent (**≥ 2 distinct `call_id`s** among `tool_dispatched` events with
  `caller: actor`, `tool: update_order`; counting events would count every F4 episode, R1-7).
- Evidence reads, re-reads, verified re-reads; cost total, per attempt and per certification at the conservative
  bound (token-priced cost separately, labelled unverified); the drift check (§11 step 8).
- **Routing: none.** The summary carries `routing: null` and the reason. No held-out request may name any Phase 28
  study or policy.

## 8. Bounds and cost

| | value | basis |
|---|---|---|
| attempts | 50, fixed; one futility look | design §6.1–6.2 |
| spend guard | **$150** at the conservative bound; no study starts once charged + **$11** > $150; the most Phase 28 can charge is **$149.23** | worst case of one study $10.23 (7 cases, unchanged) |
| expected cost **[est]** | about **$35** if the Mechanic never writes the step and the look falls near attempt 24; **up to $72** if D ≥ 16 is never reached; $49 / $64 / $78 / $86 / $99 / $112 at *s* = 0.02 / 0.05 / 0.10 / 0.15 / 0.27 / 0.40 | design §6.4 (`prep/design_numbers_r1.py`) |
| P(k ≥ 1) **[est]** | 0.14 / 0.37 / 0.66 / 0.83 / 0.97 at *s* = 0.02 / 0.05 / 0.10 / 0.15 / 0.27 | design §6.3 |
| resolution | 0 of 50 → Wilson [0, 7.1%]; 1 → [0.4%, 10.5%]; 3 → [2.1%, 16.2%] | design §6.3 |
| breaker false trip **[est]** | 0.07% at a 1-in-9 death rate, 3.4% at 25%, 15% at 35% | design §6.4 |
| study timeout / duration | 90 minutes per study / about 2.5–3.5 hours | Phase 23 |
| budget | $672.48 charged, **$327.52 remaining** after Phase 30 ($17.98) and Phase 28a ($1.60), before Phase 28. Above $300, so the budget rule below leaves the cap at $150 unless the remaining budget at approval has fallen | `CLAUDE.md`, "After Phase 28a" (updated in review round 2); restated at approval |

**Budget rule:** at approval, if the remaining budget is under $300, the cap is lowered to (remaining − $150) and N
stays 50; the approval record states the remaining budget. A lowered cap is a code constant (`SPEND_CAP`), so it
moves the plan hash and is set before F8.

## 9. Sequencing, landing, freeze and configuration-hash procedure

Every step runs from the repository root of the **main checkout** unless it says otherwise. Outputs go to
`artifacts/phase28-<date>/`, where `<date>` is the landing date (the header's "Evidence folder"). Each sha is taken
only after every value inside its file is final, and **no sha is ever written into the file it depends on**.
`<preserve>` below is `artifacts/builds/phase28-2026-09-25-r<N>/` for the last closed round N (P0), and `<build>` is
**`<preserve>/build`**, the copy F0 step 2 has just checked (review round 3, R3L-3). The worktree is only a fallback,
if that copy cannot be used; either way F0 step 3 ties the whole protocol in `<build>` to round N's record.

**The build files** (seven, "the build" below): `backend/app/lab/completion_study.py`, `backend/app/lab/api.py`,
`backend/tests/lab/test_completion_manifests.py`, `backend/tests/experiments/test_run_gap_probe.py`,
`scripts/experiments/run_upgrade_loop.py`, `backend/tests/experiments/test_run_upgrade_loop.py` and this document.
Round N's closed state is `reviewed-build-rN.json`: the whole-file sha256 of all seven, the sha256 of this document's
**declared text** (every byte above its `## Review log` heading), the prep scripts and their outputs, and the
evidence the Review log cites. The landing check pins the six code and test files whole and this document's declared
text only. This document as a whole is bound later, by **P** at F9 and in `review.json` (review round 2, WB-2).

**The one rule for review rounds (review round 2, LN-2 and WB-2).**
- **Every review round happens in the worktree, before F0:** its fixes, its Review-log entry and its closure. Only
  the last closed round lands.
- **Closing a round, even one that changed nothing but the log:**
  1. its Review-log entry is appended in the worktree, below `## Review log`, so no pin moves;
  2. `make_reviewed_build.py --round N`, run with the main checkout's venv interpreter, writes
     `reviewed-build-rN.json` beside it (both in the scratch folder `p30-28/p28-final/`; every `p30-28/` path in this
     document is in the session scratchpad);
  3. if the round changed a build file or a prep script, its fixer has already updated the landing check's
     `REVIEWED`, `REVIEWED_PROTOCOL_BODY` and `REVIEWED_PREP` (and `freeze_compare_p28.py`'s reviewed values if
     `completion_study.py` moved) as part of those fixes, and the next round reviews them. A log-only closure
     updates none of them;
  4. P0 preserves that round, into a new folder;
  5. before its first edit, the next round's fixer snapshots the round's seven build files into
     `p30-28/p28-final/r<N>-build/`, and its prep folder into `r<N>-prep/` if the fixes will change the prep. The next
     record checks both against round N's record, and the next preserve keeps them (`build-r<N>/`, `superseded/`).
     It also adds its round's evidence folders to `make_reviewed_build.py`'s patterns (review round 3, R3-3).
- **No review round runs after landing** (this replaces the design's F3; §2 row 11). A finding after F0 that needs any
  change to a build file returns to the worktree. That includes a new declared skip (§3.3) and any edit to this
  document other than the F7 and F9 fills. The landing is rolled back first:
  - copy the three pre-change copies back from `artifacts/phase28-<date>/pre-change/`;
  - move the four new files to `artifacts/phase28-<date>/rolled-back-<n>/`;
  - `landing_check_p28.py --before` (with a new `--gate-freeze-before` file name) must pass again.
  Then the round is reviewed and closed as above, and the steps restart at F0 in the same evidence folder, with a
  `-<n>` suffix on every new output.

- **P0. Preserve each closed round durably (review round 1, IN-1; review round 2, WB-6 and LN-1).** The worktree and
  every scratch folder are under `/private/tmp`, which macOS purges. The fixers can write only there, so this step is
  the owner's (or a workflow step allowed to write `artifacts/`). Run it once per closed round, **before the next
  round's fixer edits the worktree**:
  - `bash p30-28/p28-final/preserve_build.sh N` (from anywhere) copies into `artifacts/builds/phase28-2026-09-25-rN/`.
    That name is outside every phase-run pattern: `slot2_probe`'s `phase2[6-9]-*`, the runner's `phase28-*` and
    Phase 28a's `phase(2[01356789]|3[0-9])-*` all look only at folders directly under `artifacts/`.
  - **What it copies:** `build/` (the seven files); `build-r1/`, `build-r2/`, … (each earlier round's seven files,
    snapshotted by the next round's fixer before any edit and checked against that round's record); every
    reviewed-build record up to round N; `prep/` (the round's prep scripts and their outputs), with
    `PREP_SHA256SUMS` written **from the record**, not from the disk; `diffs/`; the reviewed gate freeze
    (`bb0b19a9…`); `evidence/` (every file the Review log and the records cite: every round's test runs and JUnit
    files, the mutation checks, the builder's exploration output behind §2 row 1, the overlay test runs behind §3.3,
    the dry plan and configuration previews, and the reviewers' and fixers' cited outputs, collected by
    non-recursive patterns that never reach an overlay or scratch tree); and `superseded/` (every earlier round's
    prep scripts, with a README that says never to run them).
  - **What it checks first:** the six code and test files, this document (its declared text, and since review round
    3 the whole file, because `build/` is what F0 lands: R3L-3), every prep file, the mutation checks and every
    earlier round's snapshot against the records. It refuses if the folder exists or would hold a
    `*manifest*.json`, or if an evidence path is a symbolic link, then writes `SHA256SUMS` and checks it. It edits
    nothing else: no git command, and nothing under `backend/`, `scripts/` or `docs/` of the main checkout.
  - **Round 1 was never preserved on its own.** Its script (`p28-fix1/preserve_build.sh`) now refuses by design,
    because round 2 moved the worktree. Round 1's state is inside every later preserve (`build-r1/`,
    `evidence/round1/`). **Round 2 is preserved** in `artifacts/builds/phase28-2026-09-25-r2/` (record
    `reviewed-build-r2.json`, sha256 `8f47f74c…`). Before any edit, round 3's fixer snapshotted round 2's seven files
    (`p30-28/p28-final/r2-build/`) and prep folder (`r2-prep/`); both equal that record.
  - The backup branch is **not** used for this: `commit_to_backup.sh` would put unlanded `backend/app` code at the tip
    of the branch that mirrors the main checkout. F11 commits after landing.
  - A later round is preserved the same way (`preserve_build.sh N`), into its own new folder. No folder is ever
    overwritten.
- **F0. Land the build.** Preconditions: the review rounds are closed (the one rule), the last round is preserved
  (P0), Phase 28a said GO, Phase 30 has ended, and Phase 29 is cancelled.
  1. `mkdir -p artifacts/phase28-<date>` (review round 2, LN-4: nothing else creates it, and the first redirect below
     would fail).
  2. Check the preserved prep against its record (LN-3):
     `(cd <preserve> && shasum -a 256 -c PREP_SHA256SUMS && shasum -a 256 -c SHA256SUMS) > artifacts/phase28-<date>/preserve-check.txt`.
  3. The landing check, before anything is copied:
     `./.venv/bin/python <preserve>/prep/landing_check_p28.py --before --from <build> --phase28a-run artifacts/phase28a-2026-09-25/live --gate-freeze-before artifacts/phase28-<date>/gate-freeze-before.json > artifacts/phase28-<date>/landing-check-before.txt`
     must exit 0, and its `script_sha256` must equal the record's `prep/landing_check_p28.py`. Its
     `build_protocol_sha256` must equal the record's `build_files['docs/part2/PHASE28_EXPERIMENT.md']` (in
     `<preserve>/records/reviewed-build-rN.json`): the check pins only the declared text, so this comparison is what
     ties the whole document that lands, Review log included, to round N's closure (review round 3, R3L-3).
     - **Pass `--phase28a-run` repository-relative, exactly as written above.** Since review round 3 the check
       refuses a malformed `--phase28a-run` or `--phase28a-readouts` before it takes the freeze, so that refusal
       writes nothing (R3L-1).
     - **If it refuses after taking the freeze** (any other problem), keep that attempt as evidence. Rename its two
       outputs with the next unused suffix, `landing-check-before-<n>.txt` and `gate-freeze-before-<n>.json` (n = 1,
       2, …), fix the cause, and run the command again with the names this step uses. The check never writes over an
       existing freeze file, and the redirect would otherwise overwrite the failed attempt's output. F11 commits
       every attempt's pair (R3L-1).

     It refuses unless all of these hold:
     - **the gate freeze:** it runs the pinned `gate_freeze.py` (`5e21c0ec…`) itself with `./.venv/bin/python`, saves
       the output to `gate-freeze-before.json` (never over an existing file), and that output equals Phase 22's
       freeze file (`8994e962…`) byte for byte, so nobody changed `backend/app` meanwhile. (Review round 2, WB-3:
       round 1's check hashed a file the operator supplied, and a copy of Phase 22's own file passed over a
       drifted tree.)
     - **the main checkout:** the three files the landing overwrites are still the base versions
       (`completion_study.py` `c3fc2234…`, `api.py` `9c3ac453…`, and `test_run_gap_probe.py` `336b485f…`, the
       version Phase 26's closed record cites), and the four new files do not exist there yet;
     - **the build:** the six code and test files in `<build>` equal their last-reviewed sha256, and this document's
       declared text equals its last-reviewed sha256. The Review log below it may have grown;
     - **the prep:** the prep scripts beside it equal their reviewed sha256;
     - **Phase 28a:** its run is final and its read-outs say GO (its own `readouts.json`; `--phase28a-readouts` only as
       §10 item 6 allows), and the 28a file format copied in the check and in the runner equals the 28a harness's
       (LN-5);
     - `PHASE30_RESULTS.md` exists, and no paid run is live.
  4. Save the pre-change copies of all three overwritten files (Phase 22 N3's pattern; all three, so a roll-back is
     possible):
     `for f in backend/app/lab/completion_study.py backend/app/lab/api.py backend/tests/experiments/test_run_gap_probe.py; do mkdir -p "artifacts/phase28-<date>/pre-change/$(dirname "$f")"; cp -p "$f" "artifacts/phase28-<date>/pre-change/$f"; done`.
     Then save the three landing diffs, one command each:
     `git diff --no-index backend/app/lab/completion_study.py <build>/backend/app/lab/completion_study.py > artifacts/phase28-<date>/landing-completion_study.py.diff`,
     and the same for `api.py` and `test_run_gap_probe.py`. **`git diff --no-index` exits 1 when the files differ,
     which they do,** so do not chain these with `&&` or run them under `set -e`. Check the saved diffs instead
     (LN-4).
  5. Copy exactly the seven build files from `<build>` to their paths, and `<preserve>/prep/` (scripts and outputs)
     to `artifacts/phase28-<date>/prep/`.
  6. The landing check again, from the copy that F4 will use:
     `./.venv/bin/python artifacts/phase28-<date>/prep/landing_check_p28.py --after --from <build> --phase28a-run artifacts/phase28a-2026-09-25/live --pre-change-dir artifacts/phase28-<date>/pre-change > artifacts/phase28-<date>/landing-check-after.txt`
     must exit 0. It checks that:
     - every landed file equals the build's byte for byte;
     - the six code and test files equal their reviewed sha256, and this document's declared text equals its
       reviewed sha256;
     - the three pre-change copies are the base files;
     - the prep copies are the reviewed ones;
     - the 28a checks hold again.

     Its `script_sha256` must equal the record's `prep/landing_check_p28.py`: the landed check checks its five
     siblings, but only against values it carries itself (review round 3, R3-2). Then check the whole landed prep
     folder, scripts **and outputs**, against the preserve's record:
     `(cd artifacts/phase28-<date> && shasum -a 256 -c -) < <preserve>/PREP_SHA256SUMS > artifacts/phase28-<date>/landed-prep-check.txt 2>&1; echo "exit $?" >> artifacts/phase28-<date>/landed-prep-check.txt`.
     It must end `exit 0`. The sum file's paths are `prep/…`, so it checks each landed file, and the redirect from
     `<preserve>` is opened before the `cd`.
- **F1. No code edit after landing** (the one rule). This document's status still says "NOT yet reviewed". The F7–F9
  fills are the only edits to build files from here on. Each is saved as a diff, and the approver reads it before F10.
- **F2. Tests after landing** (pitfall 75), from `backend/`:
  `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs tests/lab/test_completion_study.py tests/lab/test_completion_manifests.py tests/experiments/test_run_upgrade_loop.py tests/experiments/test_run_full_loop.py tests/experiments/test_run_full_loop_fixed_n.py tests/experiments/test_run_gap_probe.py tests/experiments/test_upgrade_mechanic_probe.py tests/experiments/test_report_narrow_probe.py > ../artifacts/phase28-<date>/tests-final.txt 2>&1`,
  then the full suite, `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs > ../artifacts/phase28-<date>/tests-full.txt 2>&1`.
  - Every failure or skip is listed and must match §3.3. In `test_upgrade_mechanic_probe.py` (Phase 28a's tests) and
    `test_report_narrow_probe.py` (Phase 30's), every store- or configuration-guarded test must skip and none may
    fail.
  - `test_run_upgrade_loop.py`'s check of the copied 28a constants (LN-5) skips in the worktree, where the 28a harness
    does not exist, and runs here. It must pass. (The round-2 fixer also ran it on a store-free overlay of the main
    checkout; Review log, round 2.)
  - If any test fails instead of skipping, that is a build change (§3.3): the one rule applies.
  - Report the intermittent `[untriggered]` failure if it appears; never call the suite unconditionally green.
- **F3. No review round after landing** (replaced; the one rule and §2 row 11). A finding from here on that needs a
  build change rolls the landing back.
- **F4. Freeze.** Every command here uses the venv interpreter, `./.venv/bin/python` (Python 3.12.8), never
  `python3`: an AST sha depends on the Python version, and `/usr/bin/python3` on this Mac is 3.9.6 (review round 1).
  - `./.venv/bin/python scripts/experiments/gate_freeze.py > artifacts/phase28-<date>/gate-freeze-after.json`, then
    `shasum -a 256 artifacts/phase28-<date>/gate-freeze-after.json > artifacts/phase28-<date>/gate-freeze-after.sha256`.
  - `./.venv/bin/python artifacts/phase28-<date>/prep/new_function_hashes.py > artifacts/phase28-<date>/new-function-hashes.json`
    must exit 0. It records the interpreter and its own sha256, and refuses under any Python but 3.12.8.
  - Accept the freeze only if
    `./.venv/bin/python artifacts/phase28-<date>/prep/freeze_compare_p28.py artifacts/phase28-<date>/gate-freeze-after.json --new-function-hashes artifacts/phase28-<date>/new-function-hashes.json > artifacts/phase28-<date>/freeze-compare.txt`
    exits 0. It checks:
    - exactly §3.4's six entries moved, and every other entry is byte-equal to Phase 22's, including `lines`;
    - **each of the six moved entries equals the reviewed value** (§3.4, whole entries: text, AST and lines);
    - the definition-hash record is ok, from Python 3.12.8, of the reviewed `completion_study.py`, and carries the
      reviewed text and AST sha of all seven definitions.
    It prints its own sha256 (`script_sha256`), which must equal the record's `prep/freeze_compare_p28.py` (review
    round 2, WB-4; F0 step 6 already checked this copy).
  - Re-run Phase 22's two held-out checks and save them (LN-4). Both must exit 0, because `heldout_check.py` is
    untouched:
    `./.venv/bin/python artifacts/phase22-2026-09-24/prep/v1_function_hashes.py > artifacts/phase28-<date>/v1-function-hashes.txt 2>&1; echo "exit $?" >> artifacts/phase28-<date>/v1-function-hashes.txt`
    and
    `./.venv/bin/python artifacts/phase22-2026-09-24/prep/phase18_reassessment.py > artifacts/phase28-<date>/phase18-reassessment.txt 2>&1; echo "exit $?" >> artifacts/phase28-<date>/phase18-reassessment.txt`.
- **F5. Expected configuration hash.** The operator runs
  `./.venv/bin/python scripts/experiments/expected_configuration.py artifacts/phase16-2026-09-22/settings-phase17.json > artifacts/phase28-<date>/expected-configuration.json`
  (it loads the root `.env` in-process; nobody opens or prints it) and cross-checks with
  `./.venv/bin/python artifacts/phase22-2026-09-24/prep/config_hash_no_env.py artifacts/phase16-2026-09-22/settings-phase17.json > artifacts/phase28-<date>/expected-configuration-no-env.json`.
  The two must agree, and their `algorithm_hash` and `runtime_hash` must equal F4's (the build preview is
  `96a30c69…`).
- **F6. Manifest hash.** `./.venv/bin/python artifacts/phase28-<date>/prep/manifest_hash.py > artifacts/phase28-<date>/manifest-hash.txt`
  and `./.venv/bin/python artifacts/phase28-<date>/prep/draft_manifest_r1.py > artifacts/phase28-<date>/manifest-mirror.txt` must print
  the same hash (the build gives `cafe5757…`), or the difference is explained and re-reviewed. The builder's
  `upgrade-3` fault spec must equal the one Phase 28a sent; otherwise the difference is reported beside the 28a
  result. (Previewed at $0 in review round 2: it equals `source_case.fault_spec` in
  `artifacts/phase28a-2026-09-25/live/plan.json`, seed 703, F4 `update_order`, `failure_count` 3.)
- **F7. Fill this document's pins** (the table below): freeze sha, configuration hash, manifest hash, supplementary
  function hashes. The "before" file is the build's copy, which F0 step 6 proved equal to the landed one (review
  round 3, R3L-2). Save the diff:
  `git diff --no-index <build>/docs/part2/PHASE28_EXPERIMENT.md docs/part2/PHASE28_EXPERIMENT.md > artifacts/phase28-<date>/f7-protocol-pins.diff`
  (it exits 1, as in F0). Then keep the filled document, which is F9's "before" file and exists nowhere else:
  `cp -p docs/part2/PHASE28_EXPERIMENT.md artifacts/phase28-<date>/protocol-after-f7.md`. **Do not take its sha yet.**
- **F8. Fill the runner's pins** (`DECLARED_MANIFEST_HASH`, `DECLARED_FREEZE_SHA256`, `DECLARED_CONFIGURATION_HASH`,
  `DECLARED_FUNCTION_HASHES`; never a protocol, runner or review-record sha). Save the diff against the build's copy
  (R3L-2):
  `git diff --no-index <build>/scripts/experiments/run_upgrade_loop.py scripts/experiments/run_upgrade_loop.py > artifacts/phase28-<date>/f8-runner-pins.diff`
  (it exits 1). Re-run `tests/experiments/test_run_upgrade_loop.py` after this last edit and save it as
  `artifacts/phase28-<date>/tests-runner-after-pins.txt`. Run the dry plan:
  `./.venv/bin/python scripts/experiments/run_upgrade_loop.py --out artifacts/phase28-<date> --settings artifacts/phase16-2026-09-22/settings-phase17.json --expect-freeze artifacts/phase28-<date>/gate-freeze-after.json --plan > artifacts/phase28-<date>/dry-plan.txt`.
  Every pin must read `MATCH` and the configuration hash `pinned`. Record **S** (the `harness sha256` line) and
  **H** (the `plan hash` line).
- **F9. Add the launch line and take the protocol's sha.** Add the bare line `Reviewed for launch: harness S plan H`
  (no backticks, list marker or bold) and replace this document's bold status sentence so that the block before the
  first `##` heading no longer contains "NOT yet reviewed". Save the F9-only diff, against F7's copy (R3L-2):
  `git diff --no-index artifacts/phase28-<date>/protocol-after-f7.md docs/part2/PHASE28_EXPERIMENT.md > artifacts/phase28-<date>/f9-protocol-launch.diff`
  (it exits 1). **Then** take **P** = `shasum -a 256` of this document. Nothing edits it afterwards.
- **F10. Approval record** `artifacts/phase28-<date>/review.json`, written only after the review rounds close.
  **First** the owner is told, in one plain sentence: "If we run Phase 28 without first sealing a new held-out test
  set, any upgrade repair it certifies can only ever be reported as a development result; it can never be checked
  on unseen cases." The record notes when. Every sha as bare 64-character hex. `phase28a` names the run's own
  read-outs; `readouts_path` is added only in the case §10 item 6 allows, and does not apply to the run below, which
  wrote its own:

  ```json
  {"phase": 28, "status": "approved", "approved_by": "Claude as PM, delegated by the project owner",
   "protocol_sha256": "<P>", "harness_sha256": "<S>", "plan_hash": "<H>",
   "gate_freeze_file_sha256": "<F4>", "configuration_hash": "<F5>", "manifest_hash": "<F6>",
   "phase_cap": 150, "remaining_budget_at_approval": "<dollars>", "decisions": "<PHASE28_DESIGN.md §11, 1-7, as taken>",
   "phase28a": {"run_dir": "artifacts/phase28a-2026-09-25/live", "decision": "GO",
                "readouts_sha256": "1c72dc35c0a6b0654714b369bb6099cff7be29270ebc0cf967c6e46e131c8a8c"},
   "reviewed_build": {"round": "<N>", "record_sha256": "<sha256 of reviewed-build-rN.json>",
                      "preserved_at": "artifacts/builds/phase28-2026-09-25-r<N>"},
   "owner_told_no_heldout_at": "<UTC time>",
   "review_rounds": ["docs/part2/PHASE28_EXPERIMENT.md#review-log"],
   "approval_basis": {"program_direction": "go ahead with whatever u recommend", "by": "Shree Bohara",
                      "date": "2026-09-25", "relayed_by": "workflow harness",
                      "scope": "the direction of Phases 28-31; each phase is still approved on its own"}}
  ```

  `reviewed_build` is a record for the reader; the runner does not check it.
- **F11. Commit and freeze** (review round 2, LN-4). Commit with Phase 22's script, which writes through a temporary
  index to the local backup branch without touching main, HEAD, the working tree or the real index, and can commit
  git-ignored `artifacts/` paths. Nothing is pushed:
  `artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "Phase 28 F11: landed build, freeze and launch records" <paths> > artifacts/phase28-<date>/backup-commit.txt`,
  with exactly these repository-relative paths:
  - **the seven build files** (on the main checkout some are untracked and some uncommitted; the script commits
    both);
  - **every file under `artifacts/phase28-<date>/prep/`** (the prep scripts and their outputs);
  - **from `artifacts/phase28-<date>/`:**
    - landing: `preserve-check.txt`, `gate-freeze-before.json`, `landing-check-before.txt`, every refused F0 step 3
      attempt's `gate-freeze-before-<n>.json` and `landing-check-before-<n>.txt` (review round 3, R3L-1), the three
      files under `pre-change/`, the three `landing-*.diff`, `landing-check-after.txt`, `landed-prep-check.txt`
      (R3-2);
    - tests: `tests-final.txt`, `tests-full.txt`;
    - freeze: `gate-freeze-after.json`, `gate-freeze-after.sha256`, `new-function-hashes.json`,
      `freeze-compare.txt`, `v1-function-hashes.txt`, `phase18-reassessment.txt`;
    - pins: `expected-configuration.json`, `expected-configuration-no-env.json` (hashes only), `manifest-hash.txt`,
      `manifest-mirror.txt`, `f7-protocol-pins.diff`, `protocol-after-f7.md` (R3L-2), `f8-runner-pins.diff`,
      `tests-runner-after-pins.txt`, `dry-plan.txt`, `f9-protocol-launch.diff`;
    - approval: `review.json`.

  From F4 until the run ends: **no edit under `backend/app`, to the runner, `gate_freeze.py`, the drift or ingestion
  checks, `completion.md`, the settings or this document**, except the F7–F9 fills.

## 10. The live gate

Dry by default. A live run needs `--execute-live --confirm-entity <entity> --expect-plan-hash H
--expect-harness-sha256 S --expect-protocol-sha256 P --review-record artifacts/phase28-<date>/review.json --settings
artifacts/phase16-2026-09-22/settings-phase17.json --expect-freeze artifacts/phase28-<date>/gate-freeze-after.json`,
and refuses before any spend unless (each is tested):
1. no pin holds `FILL-AT-FREEZE`;
2. sha256(runner) = S; sha256(this document) = P; the recomputed plan hash = H (the plan never reads this
   document, so there is no hash cycle);
3. the block before the first `##` heading does not contain "NOT yet reviewed" (any case), and a bare line reads
   exactly `Reviewed for launch: harness S plan H`;
4. every file pin matches: the settings, `completion.md`, the base and fixed-N runners, `slot2_probe.py`,
   `gate_freeze.py`, the drift and ingestion checks, the Phase 17 launcher, and the freeze file;
5. the declared freeze carries the unchanged `assess_pairs`, `case_manifest` and `planned_slots` (text and lines),
   `scorer_hash` and `completion.md`; the seven new definitions on disk equal `DECLARED_FUNCTION_HASHES`;
6. the review record says `approved`, names the approver, and repeats P, S, H, the freeze sha, the configuration
   hash and the manifest hash; and its `phase28a` names a final Phase 28a run that said GO (review round 1): `run_dir`
   is `artifacts/phase28a-<date>/<name>`, that run's manifest is final (status COMPLETED, STOPPED or ABORTED, with
   `ended_at`), the read-outs have the 28a read-out schema and decision GO, the record's `decision` is GO, and
   `readouts_sha256` is the read-outs file's sha256. **The read-outs file (review round 2, WB-5)** is the run's own
   `readouts.json`. Only when a final run wrote none (its read-outs raised, or it was closed with
   `--finalize-abandoned`) may `readouts_path` name the declared recomputation
   `artifacts/phase28a-<date>/readouts-recheck.json`: the operator's saved output of
   `./.venv/bin/python scripts/experiments/upgrade_mechanic_probe.py --readouts <run_dir>`, which prints plain
   read-outs only when the run's own harness and plan match. A recomputation wrapped under `label` (printed with
   `--not-the-runs-harness`), any other path, or a recomputation beside a run that wrote its own `readouts.json` is
   refused. Without this, a real GO whose read-outs failed to save could be refused for good, and the only way past
   would be a file written by hand into a closed run folder. Phase 28a's run wrote its own, so the fallback does not
   apply to it. Its date folder also holds a `readouts-recheck.json`, which is never used while the run's
   `readouts.json` exists;
7. the entity and project match the settings; the backend builder's `upgrade-v1` hash equals the pin; the code on
   disk equals the freeze;
8. no other paid run is live (`slot2_probe.live_experiment_processes`: a Python process running
   `experiments/<name>.py` with `--execute-live` or a prefix of it, excluding this process, its ancestors and its
   descendants, so its own `caffeinate -is` helper does not block it), checked before the claim, after the claim and
   before every attempt;
9. every process on :8000 is a non-reload uvicorn started after the newest `backend/app` file; the backend is idle;
   ingestion is healthy; and the first campaign's configuration hash equals the pin, at $0.

## 11. Runbook

Record every step under `artifacts/phase28-<date>/`. The Phase 23 runbook (`PHASE23_EXPERIMENT.md` §9) applies
unchanged except for the file names:

0. **Preconditions:** the review rounds closed in the worktree (§9, "the one rule"); P0 and F0–F11 done; the dry
   plan shows every pin `MATCH`; no `artifacts/phase28-*/upgrade-loop-manifest.json` exists; `review.json` written.
1. **Ingestion health:** `./.venv/bin/python scripts/experiments/check_ingestion_health.py > artifacts/phase28-<date>/ingestion-health.txt`
   exits 0 (the runner runs it again and refuses otherwise; Phase 12).
2. **Simulator by rule** (Phase 19, Phase 20 §9 step 2): keep it only if its command line has
   `--timeout-keep-alive 75`, its working directory is this checkout's `backend/`, and nothing it imports changed
   after it started; otherwise restart it **only** with `nohup scripts/start-simulator.sh > artifacts/phase28-<date>/simulator.log 2>&1 &`.
3. **Dashboard closed** (pitfall 82): close every dashboard tab; stop the Vite server on :5173; the backend's request
   log stays still for 10 s; `./.venv/bin/python artifacts/phase19-2026-09-23/diagnosis/loop_latency.py 20 > artifacts/phase28-<date>/loop-latency.txt`
   shows **p99 < 100 ms**.
4. **Restart the backend deliberately on the frozen code:** idle (`active_campaign_id: null`, no QUEUED or RUNNING
   study); stop it; start `nohup ./.venv/bin/python artifacts/phase17-2026-09-23/launch_backend.py >> artifacts/phase28-<date>/backend.log 2>&1 &`
   (`78911a29…`, non-reload; never `start-backend.sh` or `start-live-backend.sh`); check `/api/health`,
   `/api/config/status` (live; Actor V3.1; Mechanic V4-Pro; no active campaign) and `/api/readiness`; **re-run the
   latency check** on the new process (p99 < 100 ms).
5. **Run**, lid open, on AC power:

   ```
   caffeinate -is ./.venv/bin/python scripts/experiments/run_upgrade_loop.py \
     --out artifacts/phase28-<date> --settings artifacts/phase16-2026-09-22/settings-phase17.json \
     --expect-freeze artifacts/phase28-<date>/gate-freeze-after.json \
     --review-record artifacts/phase28-<date>/review.json \
     --expect-plan-hash H --expect-harness-sha256 S --expect-protocol-sha256 P \
     --execute-live --confirm-entity shreetbohara-quinstreet 2>&1 | tee -i artifacts/phase28-<date>/runner.log
   ```

6. **During the run** nothing else touches the backend, the simulator or the store: no dashboard, no other study, no
   probe, no other paid run.
7. **At the end** the runner writes the summary and runs the drift check. An early stop is reported to the user;
   continuing needs their approval (§6.4).
   - **If the runner died after a final stop** (the run record's stop is final but its last session has no
     `ended_at`), **run the resume command once before steps 8 and 9** (review round 3, R3-1; §6.3): step 5's
     command with `--resume` added, its output saved to `artifacts/phase28-<date>/resume-write-up.txt` instead of
     `runner.log`, so the run's log is never overwritten. It passes the same launch gates at $0, refuses the final
     stop without starting anything, and first writes the missing end fields; it needs no approval. Reconcile
     (step 9) reports this state as a discrepancy until the resume has run.
8. **Clock drift by hand** (Phase 19): `./.venv/bin/python scripts/experiments/check_clock_drift.py --store artifacts/lab.sqlite3 --since <started_at> --worlds --require-worlds > artifacts/phase28-<date>/drift-check-manual.txt; echo "exit $?" >> artifacts/phase28-<date>/drift-check-manual.txt`.
   It must agree with the record's `clock_drift`. Any drift or masked fault is a lab defect reported beside the
   result; it never earns a re-run.
9. **Reconcile:** `./.venv/bin/python scripts/experiments/run_upgrade_loop.py --out artifacts/phase28-<date> --reconcile`
   reports 0 discrepancies and 0 untracked full studies. A discrepancy saying the last session never ended means
   step 7's resume was skipped: run it, then steps 8 and 9 again.
10. **Write-up:** `PHASE28_RESULTS.md` with §7's read-outs in their declared wording and every attempt's funnel row.

## 12. What each result would and would not mean

- **k ≥ 1, the certified policies re-send the upgrade and it fires.** *Would mean:* the same loop with the
  transposed gate (backend change B1/B2: the manifest choice and `source_clause`) produced a certified repair for a
  second, upgrade-side gap **on development cases**, with L ≥ B0 on the expected outcome in 3 paired trials on
  each guard (`healthy`, the refusal case, the delayed upgrade, the unrecoverable upgrade and
  `lost-upgrade-response`), at a rate inside the Wilson interval. Guards where no rule ran are labelled "not
  exercised" (§7.4), and on `lost-upgrade-response` no gated rule can run. *Would not mean:* ACCEPTED; held-out
  safety; that it closes the notification gap; that its notification-side rules are safe; that it works beyond
  counts 2–3; a difference from Phase 23; generalisation; "no regression" beyond what 3 paired trials per guard can
  show.
- **k ≥ 1, but a certified policy has no orders re-send.** Reported as certified and flagged as not explained by the
  step.
- **k = 0 at `fixed_n`, with R ≥ 1.** "0 of 50 (Wilson upper bound 7.1%)". The funnel names where attempts were lost
  (controls leak, a step that never fires, the source-gate leak, dirty batches, clean rejections by case including
  the transposed clause, condition 3). It does not mean "impossible".
- **`futility`.** The Mechanic did not transfer the re-send to the upgrade even with upgrade evidence in view (0 of
  D, upper bound about 19%), after a 28a GO. Another brief, temperature or model might.
- **OBSERVED_IMPROVEMENT but not certified.** It passed the transposed gate but had no fresh gain; stated beside the
  primary. A source below 3 of 3 cannot appear here: the backend records it as NO_CHANGE.
- **Truncated at the cap.** Many attempts reached validation, which is upstream success. Quoted at n = j, never
  topped up.
- **Breaker or abort, not resumed.** Not a finding about the loop.

## 13. Limits

- **No held-out check can follow** (design §10): heldout-2 is spent; the promotion partition holds a
  transient-upgrade case in the fault family tuned on here; a new partition needs its own backend change and a seal
  before the policy. Every write-up says the result is development-only.
- **Correlated Mechanic draws** (temperature 0, correlated but not identical): the effective n is below 50;
  distinct-hash accounting is reported.
- **The baseline re-sends the upgrade itself** (10–17% per `upgrade-3` episode): about 4 attempts in 10 stop at
  controls and a working candidate fails the source gate about 1 time in 3 **[est]**. Declared; never loosened
  (pitfall 26).
- **Guards from 6 baseline episodes each** (`delayed-upgrade`, `lost-upgrade-response`): a lapse can read as a
  regression (about 5% of batches each **[est]**); reported as its own rejection reason.
- **Notification-side rules are never exercised**; the scope sentence says so every time.
- **Actor report slips** (PENDING for UNKNOWN, ~2%), now mostly on `upgrade-18`; reported as rejection reasons.
- **Lab defects** (dashboard freeze, keep-alive race, clock drift): the runbook and the drift check; reported, never
  re-run.
- **Pooling:** the cumulative count is a count only.

## 14. What must not happen

- No edit under `backend/app` on the main checkout before Phase 28a returned GO **and** Phase 30 ended; on a 28a
  NO_GO, never.
- The early build (§2 row 9) is never an argument in Phase 28a's review, its decision, or any approval to relaunch
  or complete it. No build file lands unless it equals its last-reviewed sha256 (F0).
- No edit to a pinned earlier-phase harness or runner; import from them.
- No edit to the gate or its inputs: `assess_pairs`, `case_manifest()`, C1–C8, `checks.py` (never opened), the brief,
  the settings. No threshold loosened after any stop.
- No held-out request of any kind naming a Phase 28 study or policy. Nobody opens heldout-2 or the promotion
  partition.
- No second chances: no operator replay, re-validation or resumption of a study; no re-test of a candidate; no stop
  at success; no top-up; no second `phase28-*` folder (the preserved builds live under `artifacts/builds/`, never in
  a `phase28-*` folder); no change to N, the cap, the look, the case set or the
  read-outs once data exists, including after Phase 28a's result.
- No sha inside the file it depends on; no protocol edit after F9; no runner edit after F8.
- Nothing called ACCEPTED; no pointer moves; nothing activated. The manual-reference policy is never a candidate and
  never shown to the Mechanic. No `private_*` record enters any model input.
- Never quoted alone: the primary always comes with the funnel, S4, the distinct certified policies, the guard
  table, the cumulative count, the Phase 28a result and the scope sentence.

## 15. Review plan

At least two adversarial rounds before F0 (landing; §9, "the one rule"), each with independent lenses: statistics
and design; the backend change (the diff, default-path identity, `source_clause` equivalence, the tests); the runner
(the copied main loop, identity, stops, the look's persistence, resume, reconcile, the guards, the allowlist);
integrity and launch (the freeze compare, the pins, the launch-gate order, sequencing with Phase 30, the worktree,
the runbook). A further round follows whenever a round changes code (pitfall 74): round 2 did, so round 3 reviewed
round 2's fixes; round 3 did too (the runner's reconcile, its tests, this document's declared text and the landing
check), so round 4 reviews round 3's fixes. Every finding and its disposition go in the Review log below; reviewer
claims that prove wrong are recorded too.

## Pins (filled at the freeze, §9 F4–F7; `FILL-AT-FREEZE` until then)

| pin | value |
|---|---|
| reviewed code freeze | `artifacts/phase28-2026-09-26/gate-freeze-after.json`, sha256 `bb0b19a9e7988884efaecec5ada22405bb520d58c16b3bdfae8c66206f6e0e8e`. The code on disk must equal it |
| expected `configuration_hash` (Phase 17 settings on the Phase 28 code) | `96a30c69b4108ff840a826141a6bce487cdeb0153a20880b7c2ffaf05659299e`. The first campaign must equal it, at $0 |
| `upgrade-v1` manifest hash | `cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3` (must equal the stdlib mirror) |
| `upgrade_case_manifest` text / AST (Python 3.12.8) | `db52a8054061e30946756b2ce1681b6849438f605cb91b1821be29c4129e4592` / `fd77006c3c04d773481bf67a5f9f0fc2ee45813a9ccc3764aa0dd86b9056ae04` |
| `CASE_MANIFESTS` text / AST | `196327a2b9c83951d893c65025d0c2bf0fc8dccac18a5d81954eac8ae9d26467` / `c1a3248afecf9b08059e49f0db483fe9a383887475f49260ebee655656ff27c3` |
| `DEFAULT_CASE_MANIFEST` text / AST | `5adef5e2bd7a4f930af30a27b0ee81856ef882f9f33dd39b825626201dd2d265` / `a064c48ec6683fc153116089dc3e0a535e15fdff14ca9f5d78c4917b7c0ff7fa` |
| `build_case_manifest` text / AST | `3220e7e912dc0e9991cdc5e281d85ca460b59be72203b204e3e9ccc17fce08a5` / `c5df4b7969ac77cca5f065a199e75d6c575f3bd1d23e01c599cdc26971a15ac3` |
| `SOURCE_CLAUSE_OUTCOMES` text / AST | `fb2a8d3622a4da6062b6a95fc42eaebf874804c60cb2a3d349149efde17a3332` / `2755d2b9998c03adc7ad6cec5a643f998d41771646fe3fceae3af546eb8b25be` |
| `SOURCE_CLAUSE_REOPENS` text / AST | `555796149da78128f156077dd0238f6db4e29c4a4e1c96672bf345013ccf4a7e` / `74874e9a5723a81f6873f2404e08a738fba1aa2f0f7e2c2307b082d00536165c` |
| `source_clause` text / AST | `4f3468cd4a904aa567e74201f68a9579c09f9f28e1557e32b0fb8db6ec78f4b9` / `51d5b4c394a788127968e5d8e6d9ce3a488775bcf1ff0852542cbf4d1402c42e` |
| settings file | `artifacts/phase16-2026-09-22/settings-phase17.json`, `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| Mechanic brief `completion.md` | `e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673` |
| base runner `run_full_loop.py` | `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342` |
| fixed-N runner `run_full_loop_fixed_n.py` | `95ef698d155986c209e1138d169b1bbb342656dd13152db457ff2185a5ff09d1` |
| `slot2_probe.py` | `28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0` |
| `gate_freeze.py` | `5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190` |
| `check_clock_drift.py` | `fa25ab9d38ed1287ff530751a4157eedffb8a0692e756bce0edef64133ae956a` |
| `check_ingestion_health.py` | `edde0190836898e2a301aadbb16906ded3ae20a5f51cd51bd4c4ee7266313c02` |
| backend launcher | `artifacts/phase17-2026-09-23/launch_backend.py`, `78911a293492b803d6c688a6044cf6e578e2b1bd6b5ccd93c65029f42aca9827` |
| `assess_pairs` text | `783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2` (lines 106–147) |
| `scorer_hash` | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` |
| default completion manifest | `7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483` |
| the runner, this document, the plan | S, P and H are on the command line and in the review record; none can appear in the file it depends on |

## Review log

### Review log — round 1 (2026-09-25)

**Who and what.** Three independent reviewers read the build read-only, at $0, each through one lens: the backend
change (BK), the runner (RN), and integrity and launch (IN). All three returned **RUN_WITH_CHANGES**, with 17
findings: 2 major and 15 minor. Two were raised by two lenses each: the Phase 28a test file's name (BK-1, IN-2) and
the unpinned module constants (BK-3, IN-4). **Every finding is accepted and applied; none is rejected.** The fixes
were made by a separate fixer, at $0, only in the worktree and its scratch folder `p30-28/p28-fix1/`. No paid,
model, provider or W&B call was made; the main checkout was not edited; no review record was written.

**Findings and dispositions.**

| # | lens · severity | finding, in short | disposition | changed in | test or evidence |
|---|---|---|---|---|---|
| BK-1 | backend · minor | F2 named the wrong Phase 28a test file (`test_mechanic_upgrade_probe.py`), and §3.3's fallout was measured before the real file (`test_upgrade_mechanic_probe.py`, harness `upgrade_mechanic_probe.py`) existed | **Fixed.** The name is corrected. The file is added to F2's targeted list. §3.3 records its guard, the expected 29 moves from passed to skipped, and that the builder's overlays predate it; F2 on the main checkout after landing is the measurement that counts | §3.3, §9 F2 | the reviewers' store-free overlays: 38 passed, 29 skipped, 0 failed, with and without the change |
| BK-2 | backend · minor | the supplementary AST pins change with the Python version; the prep script said `python3` (3.9.6 here), which would give false DIFFERS and invite re-pinning | **Fixed.** F4 and F6 run every prep script with `./.venv/bin/python`, and the prep docstrings say so. `new_function_hashes.py` records the interpreter and refuses under any Python but 3.12.8. `freeze_compare_p28.py` refuses a record from another Python. The runner's dry plan prints the interpreter | §3.4, §9 F4 and F6; prep scripts; `run_upgrade_loop.py` | reproduced: under 3.9.6 three AST shas differ, the script exits 1, and the compare refuses its output (`prep/new_function_hashes.python39-refused.out.txt`, `prep/freeze_compare_p28.negative-controls.out.txt`) |
| BK-3 | backend · minor | `DEFAULT_CASE_MANIFEST`, `SOURCE_CLAUSE_OUTCOMES` and `SOURCE_CLAUSE_REOPENS` were bound only by the file sha; `SOURCE_CLAUSE_REOPENS` decides whether `source_clause` acts at all | **Fixed by pinning** (the first option; the constants stay where they are, so `completion_study.py` is unchanged by this round). The supplementary pins are now seven definitions, in the runner, the prep script, §3.4 and the Pins table | `run_upgrade_loop.py` (`NEW_DEFINITIONS`), `new_function_hashes.py`, §3.4, Pins | `test_every_module_level_definition_the_phase28_code_added_is_pinned` (every top-level name after `_execute` must be pinned); `test_a_changed_clause_constant_moves_its_pin_and_leaves_the_function_pin_alone` |
| BK-4 | backend · minor | the equivalence property test covered only two reduced 4-case orders with narrow ranges | **Fixed.** A seeded random property test over `build_case_manifest('upgrade-v1')` in its real order: 1,000 draws, per-trial outcomes (B0 also VIOLATION), an occasional L C6. It asserts that the draws reach both decisions, the clause over a stored gain and over a stored NO_CHANGE, a candidate check failure and a regression | `test_completion_manifests.py` | `test_source_clause_equals_the_reference_on_the_full_manifest_in_its_real_order` (about 1 s); mutation check below |
| BK-5 | backend · minor | the route test accepted any status ≥ 400 for an unknown manifest id, so a crash in the builder would pass | **Fixed:** 409 and the message `Unknown completion case manifest` | `test_completion_manifests.py` | mutant B3 (KeyError, 404) killed |
| RN-1 | runner · **major** | an integrity failure found by `recover()` (on resume, or in the sweep after an abort) only marked the row; the run went on, and `abort_detail` still named the earlier cause | **Fixed, as proposed and slightly generalised.** Any integrity failure on record that no recorded stop names becomes the recorded abort before anything else happens. On resume, the resume that finds it refuses before any campaign, and records it in `abort_detail` and `resume_refusals`. In the sweep after an abort, the stop is `aborted` and `abort_detail` names it first. The next `--after-abort`, given with it in view, continues. The builder's test that relied on the old behaviour is replaced | `run_upgrade_loop.py` (`unreported_integrity_failures`, both sweeps); §6.2 | `test_an_integrity_failure_recovered_on_resume_becomes_the_abort_and_refuses_that_resume`; `test_an_integrity_failure_found_by_the_sweep_after_an_abort_is_the_recorded_abort` |
| RN-2 | runner · minor | a futility stop could be left without a summary or `ended_at` (a crash after the look's save), or rewritten as `aborted` (a signal before the break) | **Fixed.** The abort handler keeps `futility` when the look record says stop, and keeps the interruption in the session record. A refused resume after a futility stop writes what is missing from the rows on record: the summary, the budget total and `ended_at`, and marks the drift check as skipped. **One choice differs from the reviewer's wording:** `ended_at` is the look's own evaluation time, not the time of the resume, so a later phase's studies stay outside the window | `run_upgrade_loop.py` (`futility_write_up`; the abort handler); §6.3 | `test_a_crash_after_the_futility_save_gets_its_summary_and_end_on_the_refused_resume`; `test_a_signal_between_the_futility_save_and_the_break_keeps_the_final_futility_stop` |
| RN-3 | runner · minor | no test pinned the look's precedence over `fixed_n` and the spend guard | **Fixed:** two tests. The spend-guard test has a control: with the look out of reach, the guard stops at the same n | tests | `test_the_look_takes_precedence_over_fixed_n_at_exactly_n`; `test_the_look_takes_precedence_over_the_spend_guard_on_the_same_iteration` |
| RN-4 | runner · minor | no test built D from slot-2 policies | **Fixed.** The test reaches D = 16 only through slot 2, and also with two valid policies per study. **Note:** the reviewer's example, "slot 1 is a refusal", cannot occur, because a Mechanic `no_change` ends the proposal loop in `_execute`. The test uses an invalid slot-1 output instead, which the loop does follow with slot 2 | tests | `test_d_counts_distinct_valid_policies_from_any_slot` |
| RN-5 | runner · minor | the allowlist test checked `base` reads only against the module's own list | **Fixed:** `REUSED_FROM_BASE` must equal design §8.3's literal list, and `base.infrastructure_death` must not be read | tests | mutant R3 killed |
| RN-6 | runner · minor | S2u(ii)'s denominator counted slot-2 duplicates and untested step candidates | **Fixed and declared before any data (§2 row 10):** qualified ÷ step candidates tested at the source gate, which is Phase 17's S2(ii). Duplicates and untested candidates are reported on their own, and the plan carries the definition | `run_upgrade_loop.py` (`stage_funnel`, `S2U_DEFINITION`); §7.2 | `test_s2u_counts_step_candidates_tested_at_the_source_and_reports_duplicates_apart` |
| RN-7 | runner · minor | reconcile never checked that a look exists where the rows cross D ≥ 16 | **Fixed:** past the first crossing j, or at a final stop, a look record with `attempt == j` is required | `run_upgrade_loop.py` (`reconcile`, `first_look_attempt`); §6.3 | `test_reconcile_requires_the_look_at_the_first_crossing` |
| IN-1 | integrity · **major** | nothing tied the reviewed code to the code that lands and is frozen; the build existed only under `/private/tmp`; F11 left out the backend files; F0 overwrote `test_run_gap_probe.py` without checking it | **Fixed in five parts:** (a) **P0**, a durable copy to `artifacts/phase28-build-2026-09-25/` (see "Open" below); (b) this log records the build's sha256, and `reviewed-build-r1.json` records all of them; (c) **F0's landing check** refuses unless the main checkout still holds the base files (including `336b485f…`), the worktree files equal the last-reviewed shas, the 28a run said GO and Phase 30 ended; it also saves the pre-change copy, and its `--after` mode re-checks the landed files; (d) **F4's compare** requires each of the six moved entries and the seven definitions to equal the reviewed values; (e) **F11** lists all seven build files | §9 P0, F0, F4, F11; prep `landing_check_p28.py`, `freeze_compare_p28.py`; `preserve_build.sh` | compare: accepts the reviewed freeze (exit 0) and refuses the unchanged tree, an edited `_execute` entry, another `tree_lab` and a 3.9.6 record (exit 1 each). Landing check run now, against the main checkout: every file check passes, and it refuses because Phase 28a has not run and Phase 30 has not ended (`prep/landing_check_p28.*.out.txt`) |
| IN-2 | integrity · minor | the same file-name error as BK-1; `test_report_narrow_probe.py` was not in F2's list | **Fixed** with BK-1; `test_report_narrow_probe.py` added to F2 | §3.3, §9 F2 | as BK-1 |
| IN-3 | integrity · minor | the backend change was built before a 28a GO, which the design forbids, without a declared departure; the runner never checked the record's `phase28a` | **Fixed.** §2 row 9 declares the early build and states that it has no bearing on 28a's review or decision (also in §14). The review record's `phase28a` is now structured (`run_dir`, `decision`, `readouts_sha256`), and the runner refuses unless it names a final 28a run whose `readouts.json` says GO and matches that sha. The landing check does the same | §2 row 9, §10 item 6, §9 F10, §14; `run_upgrade_loop.py` (`phase28a_problem`) | `test_the_review_record_must_name_a_final_phase28a_run_that_said_go` (10 cases); `test_a_phase28a_run_that_did_not_end_on_go_refuses` (4); `test_a_final_phase28a_go_passes_whatever_way_the_run_ended` |
| IN-4 | integrity · minor | the same unpinned constants as BK-3 | **Fixed** with BK-3 (pinning, not moving the constants into `source_clause`) | as BK-3 | as BK-3 |
| IN-5 | integrity · minor | §12 overclaimed: "the unchanged loop", and "no regression" on guards where no rule can run | **Fixed** with the reviewer's wording: "the same loop with the transposed gate (backend change B1/B2) …, with L ≥ B0 on the expected outcome in 3 paired trials on each guard; guards where no rule ran are labelled not exercised (§7.4)" | §12 | — |

**Mutation check of the new tests** ($0, on a scratch copy; `p30-28/p28-fix1/mut/mutate.py` → `mutate.out.txt`). Each
mutant undoes one fix or reproduces a mutant that survived round 1. **All 18 are killed.**
- **Runner, 14:** look after `fixed_n`; D counts slot 1 only; `base.infrastructure_death` allowed; look after the
  spend guard; both integrity sweeps reverted; the futility handler reverted; the futility write-up reverted; S2u
  counts duplicates; reconcile's look check removed; the 28a check removed; its GO check removed; its sha check
  removed; the three constants unpinned.
- **Backend, 4:** each of the two reason strings dropped from `SOURCE_CLAUSE_REOPENS`; an unknown id raising
  `KeyError`; the regression replay removed from `source_clause`.

**Reviewer claims re-checked by the fixer** (read-only, $0):
- the Python 3.9.6 against 3.12.8 AST difference (three functions differ);
- the reviewed freeze: `p28-build/gate-freeze-worktree-final.json` and the backend reviewer's regeneration are the
  same file (sha256 `bb0b19a9…`);
- the main checkout's base shas (`c3fc2234…`, `9c3ac453…`, `336b485f…`), and that the four new files are absent there;
- the 28a overlay counts, from the reviewers' saved outputs;
- the four surviving runner mutants of round 1, re-created and now killed.

No reviewer claim was found wrong. RN-4's example is noted above. The finding stands.

**Not changed by this round:**
- `completion_study.py` (`03e3d8be…`) and `api.py` (`32a1b087…`), so the freeze preview, the configuration preview
  (`96a30c69…`) and the manifest hash (`cafe5757…`) are unchanged. The builder and the stdlib mirror were re-run and
  give the same output.
- `test_run_gap_probe.py` (`03dd92e2…`) is unchanged.

**The build after the round-1 fixes** (the input to round 2; sha256):

| file | sha256 | changed in this round |
|---|---|---|
| `backend/app/lab/completion_study.py` | `03e3d8bed4cbcc117ffdbb9f552f254cd33234d177e6b58254aba3f398a1b9c4` | no |
| `backend/app/lab/api.py` | `32a1b0873dd83baf7c57ec4f610d400b87179fe6adb1a88d4d901145da813283` | no |
| `backend/tests/lab/test_completion_manifests.py` | `fb352a62314bc520d2dafe92533a0674be1aca62a591432243fea82ec9e8f359` | yes (was `409ed329…`) |
| `backend/tests/experiments/test_run_gap_probe.py` | `03dd92e21c3e0908a068971eaf101a442cf5daf5dbf27bef674161e806b6f2a0` | no |
| `scripts/experiments/run_upgrade_loop.py` | `ea45d772e040c7e14da1fbf5d93370a5f1e710aa28678570e2ad8e53ae56175e` | yes (was `87b50da3…`) |
| `backend/tests/experiments/test_run_upgrade_loop.py` | `e8af59bf735fbf9a31da13df4505c344201d9b9fe8a0bd3d23a30e80aa96b972` | yes (was `64bebdfc…`) |
| this document | cannot appear in itself: see `p30-28/p28-fix1/reviewed-build-r1.json` | yes (was `2a2e7d9f…`) |

The prep scripts and their outputs are listed with their shas in `reviewed-build-r1.json`. The prep scripts are
`manifest_hash.py`, `draft_manifest_r1.py`, `new_function_hashes.py`, `freeze_compare_p28.py`,
`landing_check_p28.py` and `design_numbers_r1.py`.

**Tests after the fixes** (worktree, main venv interpreter, from `backend/`, `-p no:cacheprovider`). This run is
of the final code, before this log was written. A re-run after this log's last edit is saved beside it in
`p30-28/p28-fix1/` as `tests-phase-final.txt` and `tests-full-final.txt`.
- **Phase files** (F2's list, minus the two files that exist only on the main checkout): **377 passed, 50
  skipped, 1 failed.**
  - The failure is `test_run_full_loop_fixed_n.py::test_a_filled_freeze_time_pin_matches_its_file[DECLARED_FREEZE_SHA256]`,
    a FileNotFoundError, because the worktree has no `artifacts/`. It is the same as in the build's own run (350
    passed, 50 skipped, 1 failed); 27 tests were added.
- **Full suite: 1,508 passed, 141 skipped, 6 failed, 12 errors.**
  - All 18 failures and errors are FileNotFoundError on `artifacts/` files, which the worktree does not have:
    the Phase 17 settings file and the Phase 22 freeze.
  - The list is test for test the same as the build's own worktree run (1,481 passed, 141 skipped, 6 failed,
    12 errors). The difference is the 27 added tests, all passing.
- Phase 30's paid run was live during these runs. The tests are $0 and in-process, and none starts an
  `--execute-live` process. The suite is not called unconditionally green.

**Open after this round:**
- **P0 has not been run.** Until it is, the build and its records exist only under `/private/tmp`.
- F0–F11 are for after a 28a GO and after Phase 30 ends.
- Round 2 reviews this state. A round 3 follows if round 2 changes code (pitfall 74).

### Review log — round 2 (2026-09-25)

**Who and what.** Two independent reviewers read the round-1 build read-only, at $0:
- **WB** ("what broke"): the round-1 fixes, the landing check, P0 and the Phase 28a precondition, probed on the
  worktree's own fixtures and on simulated landings in scratch copies of the main checkout;
- **LN** ("launch rehearsal"): P0 and F0–F11, rehearsed step by step in scratch overlays of the main checkout.

Both returned **RUN_WITH_CHANGES**, with 12 findings: 2 major (LN-1, LN-2) and 10 minor. Three were raised by both
reviewers: the protocol pin in F0 (WB-2, LN-2), the unverified prep scripts (WB-4, LN-3) and P0 (WB-6, LN-1).
**Every finding is accepted and applied; none is rejected.**

The fixes were made by a separate fixer, at $0, only in the worktree and in its scratch folder `p30-28/p28-final/`.
- No paid, model, provider or W&B call was made. The main checkout was not edited. No review record was written, and
  no review was closed.
- `gate_freeze.py` was not run on the main checkout or on any copy of it, because it hashes `checks.py`. The landing
  check that now runs it (WB-3) was tested on synthetic checkouts with a fake `gate_freeze.py`.
- **Before any edit,** the fixer copied round 1's seven build files to `p30-28/p28-final/r1-build/`. All seven equal
  `reviewed-build-r1.json`, so round 1's state survives the round-2 edits (WB-6's second option).

**Findings and dispositions.**

| # | reviewer · severity | finding, in short | disposition | changed in | test or evidence |
|---|---|---|---|---|---|
| WB-1 | WB · minor | the round-1 futility write-up decided what was missing by whether a key existed. On a resumed run whose last session died after the look's save, it kept session 1's budget total ($10 against $32 spent), end time and drift result, so reconcile missed a foreign study from session 2. And the abort handler's own `print` re-raised a closed pipe's `BrokenPipeError` out of `main()`, so §6.3's own example left no summary, no end time and no record of the interruption | **Fixed, as proposed.** The write-up is keyed off the last session: if it has no `ended_at`, the total is read again, the summary recomputed, `ended_at` (run and session) set to the look's evaluation time, and `clock_drift` marked skipped in the run and session records. Earlier sessions keep their own drift results. Every field written is named in the refusal and in `futility_write_ups`. The abort handlers and the write-up print through `say()`, which drops a write error; output inside the loop still uses `print`, so a closed pipe there is a recorded abort. §6.2 and §6.3 are corrected | `run_upgrade_loop.py` (`futility_write_up`, `say`, the handlers); §6.2, §6.3 | `test_a_crash_after_the_futility_save_in_a_resumed_session_writes_that_sessions_end_fields` (the reviewer's two-session case: total 32, `ended_at` = look time, drift skipped, session 1's record kept, reconcile flags the foreign study); `test_a_closed_pipe_after_the_look_keeps_the_final_futility_stop_and_its_whole_write_up`; `test_a_closed_pipe_inside_the_loop_is_a_recorded_abort_and_nothing_escapes_main`; mutants W1–W8 |
| WB-2 | WB · minor | F0 pinned the protocol like code, but every round and the closure write to it, so the last log entry would make F0 refuse unless someone re-pinned outside a round's fixes | **Fixed by the second option:** the landing check pins the protocol's **declared text** (every byte above `## Review log`, `REVIEWED_PROTOCOL_BODY`) and the six code and test files whole. A log-only closure moves no pin. §9 states that the protocol as a whole is bound by P at F9 and in `review.json`. `--after` also requires every landed file, the protocol included, to equal the build's byte for byte | prep `landing_check_p28.py`; §9 | `prep-tests/test_landing_check_p28.py::test_wb2_a_log_only_closure_passes_and_an_edit_above_the_log_refuses`; landing mutant L4 |
| WB-3 | WB · minor | the landing check only hashed the freeze file it was given, so a copy of Phase 22's own file passed over a drifted `backend/app` | **Fixed, as proposed.** `--before` runs the pinned `gate_freeze.py` (`5e21c0ec…`, checked first) with `<main>/.venv/bin/python`, writes its output to `--gate-freeze-before` (never over an existing file) and compares it with Phase 22's file (`8994e962…`) byte for byte, listing the differing entries | prep `landing_check_p28.py`; §9 F0 step 3 | `test_wb3_a_drifted_tree_is_refused_even_with_a_copy_of_phase22s_file_at_hand` (the reviewer's scenario); `test_an_unpinned_gate_freeze_script_or_a_missing_folder_refuses`; landing mutants L1–L3 |
| WB-4 | WB · minor | nothing checked that the prep copy F4 runs is the reviewed one; P0 stored the builder's old `freeze_compare_p28.py` (no round-1 checks) beside the fixed one | **Fixed.** The landing check verifies its sibling prep scripts against `REVIEWED_PREP` in both modes (`--after` runs from `artifacts/phase28-<date>/prep/`, the copy F4 uses) and prints its own sha256. `freeze_compare_p28.py` and `new_function_hashes.py` record their own sha256 in their output. The preserve writes `PREP_SHA256SUMS` from the record, and F0 checks it. Earlier rounds' prep goes to `superseded/` with a README that says never to run it | prep `landing_check_p28.py`, `freeze_compare_p28.py`, `new_function_hashes.py`; `preserve_build.sh`; §9 P0, F0, F4 | `test_wb4_a_changed_prep_sibling_refuses`; landing mutant L5; reproduced: `grep -c REVIEWED` gives 11 in round 1's script and 0 in the builder's |
| WB-5 | WB · minor | Phase 28 accepted a 28a GO only from the run's `readouts.json`, which 28a writes only when its read-outs compute; a real GO without that file would be refused for good | **Fixed by the first option.** The review record's `phase28a` may add `readouts_path`, allowed only when the final run wrote no `readouts.json`, and only as `artifacts/phase28a-<date>/readouts-recheck.json`: the saved output of `upgrade_mechanic_probe.py --readouts <run_dir>`, which prints plain read-outs only for the run's own harness and plan. A recomputation wrapped under `label`, any other path, or a recomputation beside a run that wrote its own is refused. `PHASE28A_RULE` (so the plan hash moves), the runner, the landing check (`--phase28a-readouts`) and §10 item 6 say the same. **Not needed for the actual run:** Phase 28a wrote its own `readouts.json` (`1c72dc35…`, GO) | `run_upgrade_loop.py` (`phase28a_problem`, `PHASE28A_RULE`); prep `landing_check_p28.py`; §10 item 6, §9 F10 | `test_a_28a_run_without_its_readouts_passes_only_with_the_declared_recomputation`; `test_the_recomputation_fallback_refuses_a_label_a_no_go_and_any_other_path` (5 cases); `test_the_recomputation_is_refused_when_the_run_wrote_its_own_readouts_and_its_sha_binds_it`; `test_wb5_the_28a_read_outs_rule`; mutants W9–W12, L7, L8 |
| WB-6 | WB · minor | P0 worked only until round 2's fixer first edited the worktree; its folder name matched the paid harnesses' other-run patterns | **Fixed.** The round-2 fixer snapshotted round 1 before any edit (above). The new `preserve_build.sh <round> [<dest>]` preserves any closed round into `artifacts/builds/phase28-2026-09-25-r<N>/`, outside every phase-run pattern, and refuses to copy any `*manifest*.json`. §9 P0 tells the owner to run it once per closed round, before the next round's fixer edits the worktree | `preserve_build.sh`; §9 P0 | rehearsed into scratch (below); the round-1 script refuses now, by design |
| LN-1 | LN · **major** | P0 had not run, and it left out the evidence the protocol and `reviewed-build-r1.json` cite (the 473-of-4,096 measurement, the overlay runs, the mutation check, the final test runs, the reviewers' outputs) | **Fixed.** The preserve copies `evidence/`: every file listed in `reviewed-build-rN.json`'s `evidence`, from the builder, the round-1 fixer, the round-1 reviewers, the round-2 reviewers and this fixer (overlays, scratch trees and store copies excluded). Each is checked against its recorded sha256 before copying, as are the mutation checks. **P0 itself is still the owner's step** and has not been run: the fixer cannot write `artifacts/` | `preserve_build.sh`, `make_reviewed_build.py`; §9 P0 | rehearsal: every file the reviewer listed as missing is in the rehearsal copy (below) |
| LN-2 | LN · **major** | nothing said how a review round is recorded or closed relative to landing; any protocol edit after round 1 made P0 and F0 refuse; both scripts were hard-coded to round 1; F3 put review rounds after landing | **Fixed: one rule, declared in §9 and §2 row 11.** Every round (fixes, log entry, closure) happens in the worktree before F0, and only the last closed round lands. Closing a round, even a log-only one, appends the log entry, writes `reviewed-build-rN.json` (`make_reviewed_build.py --round N`) and preserves into a new folder (`preserve_build.sh N`). A log-only closure moves no pin (WB-2). F3 is replaced by "no review round after landing": a finding after F0 that needs a build change rolls the landing back (pre-change copies of all three overwritten files are now saved) and restarts at F0 | §2 row 11, §9 (the one rule, P0, F0, F1, F3), §15; `preserve_build.sh`, `make_reviewed_build.py` | the reviewer's scenario (a log line after round 1) now passes the landing check (`test_wb2_…`) |
| LN-3 | LN · minor | the scripts that carry the reviewed values were never checked against their reviewed sha256 when copied or used | **Fixed** with WB-4: the preserve checks every prep file against the record, writes `PREP_SHA256SUMS` from the record, F0 step 2 runs `shasum -a 256 -c` on it, and the landing check checks its siblings | as WB-4 | as WB-4 |
| LN-4 | LN · minor | runbook mechanics: (a) `<date>` said "the run's date"; (b) nothing created the evidence folder; (c) the landing diffs exit 1; (d) F4's two re-runs had no path or saved output; (e) F11 named no commit tool or file list | **Fixed, each as proposed.** (a) `<date>` is the landing date, for every step and for `--out`; (b) F0 step 1 is `mkdir -p`, and the landing check names it when the folder is missing; (c) F0 step 4 and F7 say the diffs exit 1 and must not be chained; (d) F4 gives the full `artifacts/phase22-2026-09-24/prep/` paths with saved outputs; (e) F11 names `commit_to_backup.sh` and lists every path | header, §9 F0, F4, F7–F9, F11 | `test_a_missing_evidence_folder_is_named` |
| LN-5 | LN · minor | the runner and the landing check copy Phase 28a's file format by hand, with no test tying them to the 28a harness | **Fixed.** `test_the_copied_phase28a_constants_equal_the_28a_harness_and_every_landing_check` reads the harness with `ast` (no import) and compares the five constants, where it writes `readouts.json`, the top-level `decision`, and the `label` of a mismatched recomputation. It also checks every preserved or landed landing check. It skips where the harness is absent (the worktree). The landing check compares the same constants at F0 | tests; prep `landing_check_p28.py`; §9 F0, F2 | run on a store-free overlay of the main checkout: passes (`evidence/ov-changed-constants-test.out.txt`), and fails for a renamed schema, a renamed `readouts.json` and a preserved landing check with another constant (`…negative-controls.out.txt`); `test_ln5_…`; landing mutant L6 |
| LN-6 | LN · minor | F2's "declared skip in the test_run_gap_probe.py pattern" would add an eighth landed file that nothing covers; §3.3's expected 28a count was stale | **Fixed.** §3.3 now says that a new declared skip is a build change: it is made in the worktree, reviewed, added to the build list, `REVIEWED`, `BASE` and F11, and the steps restart at F0 under the one rule. The 28a expectation is restated as "every store- or configuration-guarded test skips and none fails" | §3.3, §9 F2 | this fixer's overlays: `test_upgrade_mechanic_probe.py` 46 passed, 31 skipped, 0 failed, with and without the build |

**Mutation check of the new tests** ($0, on scratch copies; `p30-28/p28-final/mut/mutate.py` → `mutate.out.txt` and
`prep-tests/mutate_landing.py` → `mutate_landing.out.txt`). **All 36 are killed.**
- **Runner, 26:** round 1's 14 mutants re-applied to the round-2 runner (R1–R14), and 12 new ones (W1–W12). Each new
  mutant undoes one round-2 fix:
  - W1–W6: the write-up keyed off keys again, or keeping an earlier session's total, end time or drift, or ending at
    the resume's time, or not recording what it wrote;
  - W7–W8: `say()` as `print()`, and the generic handler printing with `print()`;
  - W9–W12: the 28a recomputation accepted beside its run's own read-outs, a label not singled out, any path
    accepted, an automatic fallback.
- **Landing check, 10 (L1–L10):** the fresh freeze not compared, an existing file overwritten, the script pin not
  checked, the whole protocol pinned, the siblings not checked, the 28a constants not compared, the recomputation
  accepted beside the run's own, a label accepted, `--after` not comparing landed files, and the pre-change copies
  not checked.

**Reviewer claims re-checked by the fixer** (read-only, $0):
- WB-1's two-session case, reproduced inside the new test: before the fix's write-up, the crashed record holds session
  1's `ended_at` and a $10 total.
- The closed-pipe escape, reproduced by mutants W7 and W8.
- WB-4's greps: 11 and 0.
- WB-5's reading of `upgrade_mechanic_probe.py`: the read-outs are written after the final save, a failure returns
  before `write_json`, and `--readouts` only prints.
- LN-5's grep: in round 1 the runner's tests mention `upgrade_mechanic_probe` only in a comment.
- The main checkout still holds the base files (`c3fc2234…`, `9c3ac453…`, `336b485f…`), and the Phase 28a harness is
  `3dacdbed…`, the sha in Phase 28a's `review.json`.

No reviewer claim was found wrong.

**What else this round checked ($0, read-only):**
- **Phase 28a has run:** COMPLETED with GO, 13 of 30 (`PHASE28A_RESULTS.md`; `artifacts/phase28a-2026-09-25/live`;
  `readouts.json` `1c72dc35…`). The header and F10 now name it.
- **F6 preview:** the builder's `upgrade-3` fault spec equals `source_case.fault_spec` in 28a's
  `live/plan.json` (`evidence/f6-preview-28a-spec.out.txt`).
- **Prep outputs, re-run on the round-2 prep:**
  - `freeze_compare_p28.py` accepts the reviewed freeze (`bb0b19a9…`) with exactly the six declared entries;
  - it refuses the unchanged Phase 22 freeze, an edited `_execute`, another `tree_lab` and a Python 3.9.6 record
    (exit 1 each);
  - `new_function_hashes.py` is ok under 3.12.8;
  - the builder and the stdlib mirror both give `cafe5757…`.
- **Store-free overlays of the main checkout,** with and without the round-2 build (`evidence/tests-ov-*-f2list.txt`,
  `evidence/ov-f2list-per-test-diff.out.txt`), over F2's targeted list:
  - per test, the only differences are the new tests: 29 in `test_completion_manifests.py` pass, and in
    `test_run_upgrade_loop.py` 118 pass and 3 skip for the missing store;
  - the constants test runs and passes there;
  - the 14 failures and errors are the same on both sides: the overlays have no `artifacts/`.

**Not changed by this round:**
- `completion_study.py` (`03e3d8be…`), `api.py` (`32a1b087…`), `test_completion_manifests.py` (`fb352a62…`) and
  `test_run_gap_probe.py` (`03dd92e2…`);
- therefore the freeze preview, the six reviewed moved entries, the seven definition hashes, the configuration preview
  (`96a30c69…`) and the manifest hash (`cafe5757…`);
- `freeze_compare_p28.py`'s reviewed values.

**The build after the round-2 fixes** (the input to round 3; sha256):

| file | sha256 | changed in this round |
|---|---|---|
| `backend/app/lab/completion_study.py` | `03e3d8bed4cbcc117ffdbb9f552f254cd33234d177e6b58254aba3f398a1b9c4` | no |
| `backend/app/lab/api.py` | `32a1b0873dd83baf7c57ec4f610d400b87179fe6adb1a88d4d901145da813283` | no |
| `backend/tests/lab/test_completion_manifests.py` | `fb352a62314bc520d2dafe92533a0674be1aca62a591432243fea82ec9e8f359` | no |
| `backend/tests/experiments/test_run_gap_probe.py` | `03dd92e21c3e0908a068971eaf101a442cf5daf5dbf27bef674161e806b6f2a0` | no |
| `scripts/experiments/run_upgrade_loop.py` | `0d4c7bd80ef63199a7c3bee40c82cabd59ec878a1687a0d759df17b69762e3d8` | yes (was `ea45d772…`) |
| `backend/tests/experiments/test_run_upgrade_loop.py` | `404b0cffdb2acd1e71776c3a9002204faea109fac9b6525aa9a5fecb64d13cf3` | yes (was `e8af59bf…`) |
| this document | whole file: cannot appear in itself (see `reviewed-build-r2.json`); declared text above `## Review log`: `82031b08b67279bf327e66491c11c9c1ebdff9c7523cb47501e77aa669315621` | yes |

**The round-2 prep** (`p30-28/p28-final/prep/`; sha256):
- `landing_check_p28.py`: `dfc05779ac713659b30a23cd869b8c5c14eaa984905f4e2659801e214c286e98` (rewritten);
- `freeze_compare_p28.py`: `1e53a42d7abce4145e8379e47279a48b92b570836a81b310589fa6f23bc5cd05` (records its own sha);
- `new_function_hashes.py`: `9dc8d889cfa908bb19d90ef81c993a2f18ffb855057a2bd18f9d638100e2ff5f` (records its own sha);
- unchanged from round 1: `manifest_hash.py` (`5b3199e5…`), `draft_manifest_r1.py` (`a49506ea…`) and
  `design_numbers_r1.py` (`7a1c413e…`).

Their saved outputs, the landing check's tests (`prep-tests/`), both mutation checks, `make_reviewed_build.py`,
`preserve_build.sh` and every cited evidence file are listed with their sha256 in `reviewed-build-r2.json`.

**Tests after the fixes** (worktree, main venv interpreter, from `backend/`, `-p no:cacheprovider`). This run is of
the final code, before this log was written. A re-run after this log's last edit is saved beside it in
`p30-28/p28-final/` as `tests-phase-final.txt` and `tests-full-final.txt`.
- **Phase files** (F2's list, minus the two files that exist only on the main checkout): **387 passed, 51 skipped, 1 failed.**
  - The failure is `test_run_full_loop_fixed_n.py::test_a_filled_freeze_time_pin_matches_its_file[DECLARED_FREEZE_SHA256]`,
    the FileNotFoundError on the missing `artifacts/`, the same as in rounds 0 and 1.
  - The 10 new tests pass. The new constants test skips here, because the 28a harness is absent from the worktree.
- **Full suite: 1,518 passed, 142 skipped, 6 failed, 12 errors.** All 18 failures and errors are the FileNotFoundError on `artifacts/` files that the worktree does not have (the Phase 17 settings file and the Phase 22 freeze), test for test the same list as round 1's (1,508 passed, 141 skipped, 6 failed, 12 errors). Per test, the only differences are the 10 new tests (all pass) and the new constants test (skipped here).
- **The landing check's own tests** (`prep-tests/test_landing_check_p28.py`, synthetic checkouts): 11 passed.
- The suite is not called unconditionally green.

**P0 rehearsal** ($0, into scratch only). `preserve_build.sh 2 <scratch destination>` is run after this log is
written, because it checks `reviewed-build-r2.json`, which is written last. Its output is saved as
`p30-28/p28-final/preserve-rehearsal.out.txt` and reported with the integration notes (`p30-28/p28-final/INTEGRATION.md`).

**Open after this round:**
- **Round 3** reviews round 2's fixes (pitfall 74). Round 2 changed the runner, its tests, this document and the
  landing check.
- **Round 2 is not closed.** The owner closes it under §9's one rule. First the closure entry is appended here. Then
  `make_reviewed_build.py --round 2` is re-run, which rewrites `reviewed-build-r2.json` with this document's final
  sha256. Then P0 runs. Round 3 reviews the closed state.
- **P0 has not been run.** Until the owner runs `preserve_build.sh 2` (or the last closed round's), the build and its
  records exist only under `/private/tmp`. It must run before round 3's fixer edits the worktree.
- F0–F11 follow the closed rounds. The preconditions Phase 28a GO and Phase 30 ended are met.

### Closure of round 2 (2026-09-26)

**Closed by** Claude (Opus 5.5) as PM, delegated by the project owner, under §9's one rule. This is a round closure,
not the launch closure (§9 F9–F10), and it approves nothing for spending.
- **Round 2's reviewers:** the what-broke lens and the launch lens, both RUN_WITH_CHANGES (12 findings: 2 major, 10
  minor). **All 12 are applied** by the round-2 fixer, and none was declined (the round-2 log above).
- **Round 2 changed code** (the runner, its tests, this document's declared text and the landing check), so **round
  3 follows** (pitfall 74, §15). Round 3 reviews this closed state.
- **Tests at closure** (the fixer's run after its last edit): phase files 387 passed, 51 skipped, 1 failed; full
  suite 1,518 passed, 142 skipped, 6 failed, 12 errors. All 19 are the known FileNotFoundError on `artifacts/`,
  which the worktree does not have. The suite is not called unconditionally green.
- **Record and preserve:** `make_reviewed_build.py --round 2` is re-run after this entry, and P0
  (`preserve_build.sh 2`) copies the build to `artifacts/builds/phase28-2026-09-25-r2/` before round 3's fixer edits
  anything. The record's sha256 is quoted in round 3's log (it cannot appear in the file it hashes).

### Review log — round 3 (2026-09-25; 2026-09-26 UTC)

**Who and what.** Two independent reviewers read the closed round-2 build read-only, at $0. That build is the record
`p30-28/p28-final/reviewed-build-r2.json` (sha256 `8f47f74c12b5d0272bd3ee0386a93b02a51d6b71439c04fc7dfde8940d244a29`),
preserved by P0 in `artifacts/builds/phase28-2026-09-25-r2/`.
- **Code** (`p30-28/r3-code/`): round 2's runner changes, the landing check and the preserve, tried with fakes, probes
  and mutants.
- **Landing** (`p30-28/r3-landing/`): P0's preserve and F0–F11, walked against the main checkout, including the first
  real run of F0 step 3 (exit 0; its gate freeze equals Phase 22's `8994e962…` byte for byte).

Both returned **RUN_WITH_CHANGES**, with 7 minor findings: 3 from the code reviewer (R3-1 to R3-3) and 4 from the
landing reviewer (R3L-1 to R3L-4). **Every finding is accepted and applied; none is rejected.**

The fixes were made by a separate fixer, at $0, only in the worktree and in `p30-28/p28-final/`. Its evidence is in
`p30-28/r3-fix/`.
- No paid, model, provider or W&B call was made. The main checkout was not edited. No review record was written, the
  round was not closed, and neither `make_reviewed_build.py --round 3` nor `preserve_build.sh 3` was run for real
  (a rehearsal in a throwaway mirror only, below).
- **Before any edit,** the fixer copied round 2's seven build files to `p30-28/p28-final/r2-build/` and round 2's prep
  folder to `p30-28/p28-final/r2-prep/`. It also copied round 2's closure scripts, landing-check tests and mutation
  script to `p30-28/r3-fix/r2-scripts/`. All of them equal `reviewed-build-r2.json`
  (`r3-fix/r2-build-snapshot-check.out.txt`, `r3-fix/r2-prep-snapshot-check.out.txt`).
- Three findings asked only for an operator note in this log or the closure (R3L-1, R3L-2, R3L-3), because a note
  there moves no pin. R3-1 moves the pins anyway, so their rules are written into §9 itself, where the operator reads
  them, and recorded here.

**Findings and dispositions.**

| # | reviewer · severity | finding, in short | disposition | changed in | test or evidence |
|---|---|---|---|---|---|
| R3-1 | code · minor | round 2's write-up completes a futility-stopped record only when a resume runs, and nothing told the operator to run one (§6.4 said "never resumed"; §11 had no step). Reconcile trusted the unfinished record: on a resumed run whose second session died after the look's save, it reported 0 discrepancies and 0 untracked studies although a foreign full study had started during session 2 (the record still held session 1's end time and $10 against $32 spent) | **Fixed, as proposed** (the reviewer's patch `r3-code/proposed-reconcile-fix.diff`, applied as written apart from the finding label in its comment). Reconcile reports any final stop whose last session has no `ended_at` as a discrepancy, and its message says to run the resume command once and then reconcile again. §6.3 says so. §6.4 now qualifies "never resumed": this resume is a write-up only; it refuses, writes the end fields, starts nothing and needs no approval. §11 step 7 says when to run it (its output goes to `resume-write-up.txt`, never over `runner.log`), and step 9 says what the discrepancy means. In practice only a futility stop can reach this state: `fixed_n` and `spend_guard` reach the disk in the same save as the end fields | `run_upgrade_loop.py` (`reconcile` and two docstrings); §6.3, §6.4, §11 steps 7 and 9 | `test_reconcile_flags_a_final_stop_whose_last_session_never_ended_until_the_resume_writes_it`, at 3 points of death: after the look's save, in the post-loop budget read, and before the end save. The crashed record holds session 1's end time and $10; `reconcile()` and `--reconcile` name the unended session (exit 1); after the refused resume, reconcile sees the foreign study. Mutants V1 and V2 |
| R3-2 | code · minor | after F0 step 5's copy, nothing checked the landed prep folder that F4 runs from: `--after` checks the five siblings only against values the landed check carries itself, its printed `script_sha256` was compared with nothing, and the prep outputs were never re-checked | **Fixed, as proposed, in §9 F0 step 6** (folded into R3-1's protocol edit). The printed `script_sha256` must equal the record's `prep/landing_check_p28.py`, and `(cd artifacts/phase28-<date> && shasum -a 256 -c -) < <preserve>/PREP_SHA256SUMS > …/landed-prep-check.txt` must end `exit 0`; F11 commits that file. One detail differs from the reviewer's form: with `-c <preserve>/PREP_SHA256SUMS` inside the `cd`, the repository-relative `<preserve>` would not resolve, so the sum file is fed on standard input, which the shell opens before the `cd` | §9 F0 step 6, F11 | the reviewer's `landed-prep-sums-check.clean.out.txt` (exit 0) and `.swapped.out.txt` (exit 1); the rehearsal below, in the protocol's own form: clean landing `exit 0`; one prep output changed after review, `FAILED` and `exit 1` |
| R3-3 | code · minor | `make_reviewed_build.py`'s evidence patterns stopped at round 2, so a round-3 record and preserve would miss round 3's evidence, against P0's rule | **Fixed.** Non-recursive round-3 patterns: `r3-*/*.txt`, `*.json`, `*.jsonl`, `*.xml`, `*.py`, `*.diff`, `*.sh` and `r3-*/tests/*.py`; r3-landing's five folders of saved outputs; and r3-fix's snapshot of round 2's scripts. A symbolic link anywhere on a matched path now refuses the record and the preserve, so an overlay's link is never followed. **Generalised for later rounds:** the record checks every earlier round's snapshot (`r1-build/`, `r2-build/`) against its record and names each record's sha (`earlier_rounds`); it lists `changed_since_previous_round`; and it adds round 2's prep (`r2-prep/`) to `superseded/`. `preserve_build.sh` copies `build-r<k>/` and `records/reviewed-build-r<k>.json` for every earlier round. `make_diffs.sh` no longer empties `diffs/`: re-running round 2's commands now would have rewritten round 2's recorded diffs against round 3's files. It writes `fix3-*.diff` beside them | `make_reviewed_build.py`, `preserve_build.sh`, `make_diffs.sh` (none is a build file or a prep script); §9 the one rule (new item 5) and P0 | `r3-fix/evidence-globs-static-check.out.txt` (the helpers only, no record written; taken mid-round, so the closure's count will be higher): 223 evidence files, 89 of them round 3's, no `*manifest*.json`, no link, and every round-2 evidence path still matched and unchanged. The rehearsal below |
| R3L-1 | landing · minor | a refused first F0 step 3 attempt uses up the file names: the check takes the freeze before it checks the `--phase28a-run` shape, the re-run must pick a new freeze name, and the redirect overwrites the failed attempt's output. F11 named only the plain pair | **Fixed, with the optional hardening.** §9 F0 step 3 now says: pass `--phase28a-run` repository-relative; if the check refuses after taking the freeze, rename that attempt's pair with the next unused `-<n>` suffix and run again with the step's names. F11 commits every attempt's pair. The landing check now also refuses a malformed `--phase28a-run` or `--phase28a-readouts` before it takes the freeze, so that refusal writes nothing. That is a prep-script change, so round 4 reviews it | prep `landing_check_p28.py` (`phase28a_arguments`, `main`, `report`); §9 F0 step 3, F11 | `prep-tests/test_landing_check_p28.py::test_r3l1_a_malformed_28a_argument_is_refused_before_the_freeze_and_writes_nothing`; landing mutant L11. On the real main checkout, the task's absolute-path form exits 1 and writes no file (`r3-fix/landing-check-before-abs-path-attempt.txt`) |
| R3L-2 | landing · minor | F7, F8 and F9 each say to save a before/after diff, but none names the "before" file, and F9's "before" (the document after F7) existed nowhere | **Fixed in §9**, not only as a note, since the declared text moved anyway. F7 and F8 diff against `<build>`'s copies, which F0 step 6 proved equal to the landed files. F7 then saves `protocol-after-f7.md`, and F9 diffs against it. F11 commits it | §9 F7, F8, F9, F11 | the reviewer's F8 and F9 rehearsals (`r3-landing/f8-rehearsal/`, `r3-landing/f9-f10-rehearsal/`) had to make these copies themselves |
| R3L-3 | landing · minor | two build sources were allowed and only one was verified whole: nothing compared the landed protocol's whole-file sha with the last record, so a line appended to the worktree's Review log after a closure would land with no closure record naming it | **Fixed in §9, and in the preserve.** `<build>` is `<preserve>/build`, the copy F0 step 2 has just verified; the worktree is only a fallback. F0 step 3 requires `build_protocol_sha256` to equal the record's `build_files['docs/part2/PHASE28_EXPERIMENT.md']`. `preserve_build.sh` now refuses unless the worktree's whole protocol is the one the record names (round 2's version only printed a note), so `<preserve>/build` always holds a protocol that a record names | §9 (the definitions, P0, F0 step 3); `preserve_build.sh` | rehearsal control 5a below: a Review-log line appended after the record makes the preserve refuse, and no folder is created |
| R3L-4 | landing · minor | the integration notes were out of date: "Nothing is durable yet", "P0 was not run", round-2 closure still to do, and a protocol sha of `ec80fbc4…` | **Fixed.** `p30-28/p28-final/INTEGRATION.md` is rewritten for round 3, and its first line says it supersedes round 2's notes. Round 2's copy stays as preserved, in `artifacts/builds/phase28-2026-09-25-r2/records/INTEGRATION.md` (`fddb9193…`) | `INTEGRATION.md` (not a build file) | — |

**Mutation check of the new tests** ($0, on scratch copies; `p30-28/p28-final/mut/mutate.py` → `mutate.out.txt` and
`prep-tests/mutate_landing.py` → `mutate_landing.out.txt`). **All 39 are killed.**
- **Runner, 28:** round 1's 14 and round 2's 12 re-applied to the round-3 runner (R1–R14, W1–W12), and 2 new ones:
  - V1: reconcile trusts a final stop whose last session never ended;
  - V2: the check keyed off the run's `ended_at`, which on a resumed run is an earlier session's, instead of the last
    session's.
  Each new mutant fails all three cases of the new test.
- **Landing check, 11:** round 2's L1–L10 re-applied, and L11: the 28a arguments not checked before the freeze.

**Reviewer claims re-checked by the fixer** ($0, read-only):
- R3-1: reproduced inside the new test (before the resume, the crashed record holds session 1's `ended_at` and a $10
  total) and by mutant V1 (without the check, reconcile returns no problem on that record, and the test fails). The
  reviewer's own probe, re-run from a copy against the round-3 worktree (`r3-fix/r3-code-probe-rerun-on-round3.out.txt`),
  gives 37 passed and 4 failed. The 4 failures are exactly the finding's assertion that reconcile says nothing before
  the resume: it now names the unended session, and after the resume it still reports the foreign study
  (`r3-fix/r3-code-probe-rerun-reconcile.jsonl`). The other 37 (every death after the look, dead consoles, the 28a
  rules, deaths during the resume's own write-up) still pass: the write-up itself was already sound, and round 3 does
  not change it.
- R3-2: in round 2's code, `--after` compares the siblings only with the `REVIEWED_PREP` the landed check carries.
- R3L-1: in round 2's code, `take_gate_freeze()` runs before `phase28a()` checks the path shape. The reviewer's saved
  attempt shows it (`r3-landing/landing-check-before-1-abs-path.txt`).
- R3L-3: at the start of this round the worktree's protocol and round 2's record agreed (`3cc4e3d2…`, this fixer's
  snapshot check), as the reviewer found for the preserve's `build/` too.
- R3L-4 and R3-3: the stale lines and the round-2-only patterns are as the reviewers quote them.

No reviewer claim was found wrong. R3-2's command form is adjusted as noted in its row.

**What else this round checked** ($0):
- **The round-3 landing check on the real main checkout** (`r3-fix/landing-check-before-real-main-worktree.txt`,
  before this log was written): `--before --from <worktree>` exits 0. It ran the pinned `gate_freeze.py` itself; the
  output (`r3-fix/gate-freeze-before.json`) equals Phase 22's freeze byte for byte (`8994e962…`). Every file check
  passes: the base files, the four new files absent, the six code and test files and the declared text as reviewed in
  round 3, the prep siblings, and the 28a format. Phase 28a is GO (`1c72dc35…`), Phase 30 has ended, and no paid run
  is live. It is re-run after this log (`r3-fix/landing-check-before-real-main-final.txt`).
- **A rehearsal of the round-3 closure tools** (`r3-fix/rehearse_close_and_preserve.py` → `.out.txt`). It runs in a
  throwaway mirror outside `p30-28/`, built from clones of exactly the files the closure reads, and it writes nothing
  in `p28-final/` or the main checkout. It checks:
  - the mirror's `make_reviewed_build.py --round 3` and the preserve's own code;
  - the rehearsal preserve's two sum files, and its `build-r1/`, `build-r2/`, records and `superseded/round2-prep/`;
  - F0 step 6's landed-prep check;
  - three negative controls: a Review-log line after the record (the preserve refuses), an evidence file replaced by a
    link (the record refuses), and a changed `r2-build/` file (the record refuses).

**Not changed by this round:**
- `completion_study.py` (`03e3d8be…`), `api.py` (`32a1b087…`), `test_completion_manifests.py` (`fb352a62…`) and
  `test_run_gap_probe.py` (`03dd92e2…`);
- therefore the freeze preview, the six reviewed moved entries, the seven definition hashes, the configuration preview
  (`96a30c69…`) and the manifest hash (`cafe5757…`);
- `freeze_compare_p28.py` and its reviewed values, the other four prep scripts, their saved outputs and
  `REVIEWED_PREP`;
- the certification rule, the case set, N, the cap, the look, the stops and the read-outs.

**The build after the round-3 fixes** (the input to round 4; sha256):

| file | sha256 | changed in this round |
|---|---|---|
| `backend/app/lab/completion_study.py` | `03e3d8bed4cbcc117ffdbb9f552f254cd33234d177e6b58254aba3f398a1b9c4` | no |
| `backend/app/lab/api.py` | `32a1b0873dd83baf7c57ec4f610d400b87179fe6adb1a88d4d901145da813283` | no |
| `backend/tests/lab/test_completion_manifests.py` | `fb352a62314bc520d2dafe92533a0674be1aca62a591432243fea82ec9e8f359` | no |
| `backend/tests/experiments/test_run_gap_probe.py` | `03dd92e21c3e0908a068971eaf101a442cf5daf5dbf27bef674161e806b6f2a0` | no |
| `scripts/experiments/run_upgrade_loop.py` | `9432419e2b7585d447924be5a603851290aecbb6adfac5385419385176da63a7` | yes (was `0d4c7bd8…`) |
| `backend/tests/experiments/test_run_upgrade_loop.py` | `1de4f5214e6048758920e2ecc2773235b9a17afb2c5c055705f92d32d4c0a73b` | yes (was `404b0cff…`) |
| this document | whole file: cannot appear in itself (see `reviewed-build-r3.json` once the round closes); declared text above `## Review log`: `672195d6155b6ab0ba0f2beb4d9e3a2b324950de7b01e7ee2bbac74ef0ee84ea` | yes (declared text was `82031b08…`) |

**The round-3 prep** (`p30-28/p28-final/prep/`; sha256):
- `landing_check_p28.py`: `07fc36ee7521d7b7dbc34731ae6afaeb5648d6d39f1411ee0b3742dde327854e` (changed: the reviewed
  values `REVIEWED`, `REVIEWED_PROTOCOL_BODY` and `REVIEWED_ROUND`, and the argument check before the freeze);
- unchanged from round 2: `freeze_compare_p28.py` (`1e53a42d…`), `new_function_hashes.py` (`9dc8d889…`),
  `manifest_hash.py` (`5b3199e5…`), `draft_manifest_r1.py` (`a49506ea…`), `design_numbers_r1.py` (`7a1c413e…`), and
  every saved output.

**Tests after the fixes** (worktree, main venv interpreter, from `backend/`, `-p no:cacheprovider`). This run is of
the final code, before this log was written (`p30-28/p28-final/tests-*-r3-prelog.txt`). A re-run after this log's last
edit is saved beside it as `tests-phase-r3.txt` and `tests-full-r3.txt`.
- **Phase files** (F2's list, minus the two files that exist only on the main checkout): **390 passed, 51 skipped, 1
  failed.** The failure is the same FileNotFoundError on the missing `artifacts/`
  (`test_run_full_loop_fixed_n.py::test_a_filled_freeze_time_pin_matches_its_file[DECLARED_FREEZE_SHA256]`) as in
  rounds 0 to 2. Per test, against round 2's JUnit file, the only difference is the 3 new cases, all passing
  (`r3-fix/per-test-diff-phase-prelog.out.txt`).
- **Full suite: 1,521 passed, 142 skipped, 6 failed, 12 errors.** All 18 failures and errors are the
  FileNotFoundError on `artifacts/` files that the worktree does not have (the Phase 17 settings file and the
  Phase 22 freeze), test for test the same list as round 2's (1,518 passed, 142 skipped, 6 failed, 12 errors). Per
  test, the only difference is the 3 new cases, all passing (`r3-fix/per-test-diff-full-prelog.out.txt`).
- **The landing check's own tests** (`prep-tests/test_landing_check_p28.py`, synthetic checkouts): 12 passed.
- The suite is not called unconditionally green.

**Open after this round:**
- **Round 3 is not closed.** Under §9's one rule, the owner appends the closure entry here, then runs
  `make_reviewed_build.py --round 3` (it now also checks `r2-build/` and `r2-prep/` against round 2's record), then P0
  (`preserve_build.sh 3`), which copies `build-r1/` and `build-r2/` beside `build/`.
- **Round 4 is required**, because round 3 changed code: the runner's `reconcile`, its tests, this document's
  declared text and the landing check. Before any edit, round 4's fixer snapshots round 3's files into `r3-build/`
  (and the prep into `r3-prep/` if it changes it), and adds round 4's evidence folders to `make_reviewed_build.py`
  (§9, the one rule, item 5).
- F0–F11 follow the last closed round, with `<build>` = `<preserve>/build`.

### Closure of round 3 (2026-09-26)

**Closed by** Claude (Opus 5.5) as PM, delegated by the project owner, under §9's one rule. This is a round closure,
not the launch approval (§9 F9–F10), and it approves no spending.
- **Round 3's two reviewers** (the code lens, `p30-28/r3-code/`, and the landing lens, `p30-28/r3-landing/`) returned
  RUN_WITH_CHANGES with **7 minor findings. All 7 are applied, and none was declined** (the round-3 log above).
- **Round 3 changed code:** reconcile in the runner, the runner's tests, this document's declared text and
  `landing_check_p28.py`. Under pitfall 74 those fixes were reviewed by an independent focused check
  (`p30-28/r3-verify/`), which tried to break each fix with $0 fakes and synthetic checkouts, re-ran the landing check
  `--before` on the real main checkout (exit 0; the freeze equals Phase 22's `8994e962…` byte for byte), rehearsed
  the record and the preserve in a mirror, **found no new defect and changed nothing.** That check is the further
  review that the header and §15 mean by "round 4 reviews round 3's fixes". So **no round-4 fixes, record or
  preserve follow; round 3 is the last closed round;** F0 uses `<preserve>` = `artifacts/builds/phase28-2026-09-25-r3`
  and `<build>` = `<preserve>/build`.
- **Round-3 sha256:** runner `9432419e…`, runner tests `1de4f521…`, declared text `672195d6…`,
  `landing_check_p28.py` `07fc36ee…`. **Unchanged:** `completion_study.py` `03e3d8be…`, `api.py` `32a1b087…`,
  `test_completion_manifests.py` `fb352a62…`, `test_run_gap_probe.py` `03dd92e2…`, and the five other prep scripts.
- **Tests at closure:** phase files 390 passed, 51 skipped, 1 failed; full suite 1,521 passed, 142 skipped, 6
  failed, 12 errors. All 19 are the known FileNotFoundError on `artifacts/`, which the worktree does not have; test
  by test the list is round 2's plus 3 new passing cases. The landing check's own tests: 12 passed. The suite is not
  called unconditionally green.
- **Operator notes** (these move no pin):
  1. the write-up resume in §11 step 7 must pass every launch gate, so the backend must be running (restart it per
     the runbook if the machine died);
  2. three rehearsal copies are **not** round 3's record and must never be used as `<preserve>`:
     `scratchpad/r3-fix-rehearsal/preserve-r3`, `p30-28/r3-verify/preserve-rehearsal` and
     `scratchpad/r3-verify-work/mirror`;
  3. a gap that predates round 3: if a run ending in `fixed_n` or `spend_guard` dies between its end save and its
     drift save, the run-level `clock_drift` is an earlier session's value. Runbook step 8's drift check by hand
     covers it, and it must be run and quoted whatever the record says.
- The whole-file sha256 of this document and the record's sha256 cannot appear in the file they hash; both are in
  `INTEGRATION.md` and go into `review.json`.
