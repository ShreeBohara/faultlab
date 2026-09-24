# Phase 22 results: build, review, freeze and seal ($0). September 23–24, 2026

Phase 22 built what Phases 23 and 24 need, had it reviewed twice, froze it, and sealed a fresh
held-out partition. No model, provider or W&B call was made. The full record is in
`PHASE22_EXPERIMENT.md` (Review log rounds 1–2, Approver decisions, Pins) and
`artifacts/phase22-2026-09-24/`.

## What was built

| item | file | status |
|---|---|---|
| held-out check v2 path: partition directory + pinned `manifest_hash`; `assess_heldout_v2` (15 trials per arm per fault case, one-sided Fisher p ≤ 0.05 OR L = 0 with B0 ≥ 3; rules 1 and 4 unchanged; v1 on the first replica stored beside it) | `backend/app/lab/heldout_check.py`, `api.py` (held-out routes only) | frozen; the v1 functions are text-identical, and Phase 18 still re-assesses to HARM / `check_failure` |
| heldout-2 generator (the Phase 20 Appendix A rule; novelty against manifest `7ab9368e` and the promotion partition, compared in code, printing nothing; the final audit never loaded) | `scripts/experiments/make_heldout_partition.py` | pinned and committed **before** the seed existed |
| predicate calibration (exact enumeration at the measured baseline rates) | `scripts/experiments/phase22_predicate_calibration.py` | re-run at the freeze; reproduces round 1 exactly |
| fixed-N loop runner (30 attempts, never stops at a certification, $150 guard, routing field) | `scripts/experiments/run_full_loop_fixed_n.py` | pins filled; dry plan all MATCH |
| Phase 24 runner (v2, $87, scripted routing from Phase 23's manifest) | `scripts/experiments/run_heldout2_check.py` | pins filled; dry plan all MATCH |
| protocols | `PHASE22/23/24_EXPERIMENT.md` | reviewed and frozen |

## Review

- **Round 1** (four lenses: statistics, integrity, runners, integration): 3 blockers and 12
  majors, all fixed.
- **Round 2** (three lenses on round 1's changes): 6 majors, all fixed.
- **Every finding and its disposition** is logged. Three reviewer claims turned out wrong or
  overstated, and the log records them.

## The v2 decision: **adopted**, with the literal non-compliance stated

- **The criterion.** The program's criterion, that v2 must match or beat v1's power on each
  harm scenario and have lower false-HARM, is **not met literally**. Its power half fails on 3,
  1 or 2 of 5 cases depending on the reading, and in substance in all three.
- **Why adopted anyway** (the approver's reasons are in the Review log):
  - under the committed reading, the only failure is the transient-upgrade case, which the
    program exempted in advance; neither design can see a loss there;
  - rule 3's per-case false HARM falls from up to 34% to at most 4%;
  - false NO_HARM against a halving falls from 0.09 to 0.01;
  - v2's main cost is fewer verdicts per attempt (INCOMPLETE), never a wrong verdict.
- **Every Phase 24 verdict must state:**
  - the transient-upgrade floor;
  - the small-loss blind spot on high-rate cases;
  - the verdict-rate cost: P(a verdict) is about 0.70 within 2 attempts and 0.84 within 3;
  - that one kind of harm on the delayed-confirmation case can only read INCOMPLETE.

## Freeze and seal

| item | value |
|---|---|
| gate freeze (only `algorithm_hash`, `runtime_hash`, `tree_lab` moved) | `8994e962…` |
| `assess_pairs` / `scorer_hash` | `783e8e58…` / `19de811c…` (**unchanged**) |
| expected `configuration_hash` (Phase 17 settings, Phase 22 code; two independent computations agree) | `2cf63e93…` |
| heldout-2 seed sha256 (committed at S2, **before** any draw; sent to the owner in chat) | `470aaac01052c177b8c2c8fa8f50f5129181ac786b9c265086d48ca195dadcff` |
| heldout-2 `manifest_hash` / file sha256 | `c902f1c9…` / `4f2aa9fc…`; 6 cases; directory 0700, files 0600; every seal check passes |
| backup-branch commits | F6 `a349061d` (generator pinned) → S2 `105ba1f3` (seed) → S5 `a1c64cac` (seal) → F11 `3f04df5e` |

- **Order of events:** the seed was committed before any draw, and before Phase 23 could
  produce any policy. Nobody has opened the seed or the partition file.
- **Commit times are operator-attested:** local clock, local unpushed branch.

## Tests

- **Full backend suite:** 1,165 passed, 0 failed, 59 skipped, all of the skips declared.
- **After the pins were filled:** the seven Phase 22 files pass 437 of 437, with no skips.
- **Test change:** `test_lapse_probe.py` gained a declared skip for its 17
  configuration-dependent tests when the tree is not Phase 21's (approver decision N3). Its
  pre-change copy is in `artifacts/phase22-2026-09-24/`.
- **The intermittent failure** seen since Phase 10 did not appear in this run. It is still
  unexplained.

## Budget

$0. Still **$506.23 conservatively charged, $493.77 remaining**.
