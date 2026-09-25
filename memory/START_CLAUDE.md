# START HERE — FaultLab continuation handoff

Written 2026-09-22 after Phase 15; updated 2026-09-23 after Phase 18. This file is the entry point. Read it fully before
touching anything.

## Where things are

- Repo: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab` (local `main`, HEAD
  `cbbf957`, with **substantial uncommitted and untracked implementation — preserve it**).
- Specs/checklist: sibling `../FaultLab_Specs/specs/001-faultlab-loop/tasks.md`.
- `artifacts/` is git-ignored and holds every database, world, freeze and run record.
  **Preserve it.** A fresh clone is not sufficient.

## What FaultLab is

A crash-test lab for tool-using agents. One supported task: upgrade a synthetic order, then
send exactly one truthful confirmation. Faults are injected (lost response after commit,
delayed terminal op, stale read, transient failure). Roles: **Actor** performs the task,
**Explorer** picks faults, **Mechanic** proposes a bounded recovery policy, a **fixed
Referee** scores C1–C8 against private truth. `assess_pairs` is the acceptance gate.

## Latest: Phases 20 and 21 (2026-09-23)

- **Phase 20 ($18.77):**
  - no baseline fails any check 3 of 3, so **ACCEPTED has no known source**;
  - the certified repair had 0 safety failures in 69 development episodes;
  - its read-out on transient upgrade failures is floor-limited.
- **Phase 21 ($22.22):** the one-line Actor fix for the lapse FAILED (3 of 65 sends). The
  lapse is a turn-3 chance draw that becomes absorbing. Temperature 0 is not deterministic.
- **Phase 22 ($0):** v2 held-out predicate adopted, heldout-2 sealed (seed sha `470aaac0…`,
  manifest `c902f1c9…`), code frozen (`8994e962…`, configuration `2cf63e93…`).
- **Phase 23 ($77.30):** **3 of 30 attempts certified** [3.5%, 25.6%], three distinct policies.
  The Mechanic writing the step (7 of 26) and slot-2 duplicates (16 studies) are the binding
  constraints.
- **Phase 24 ($17.12):** the routed policy `711bddb6…` was HARM on heldout-2. One Actor report
  said PENDING where the evidence said UNKNOWN (C5/C6); the policy acted correctly. Held-out
  safety is unshown again, and heldout-2 is spent.
- **Phase 25 ($12.96):** no slot-2 change was recommended. With no prior candidate in view,
  the Mechanic never copied slot 1 (0 of 26, a descriptive lead).
- **Phase 26 ($17.05):** a manual-reference policy that re-sends the upgrade completes 36 of 36
  upgrade-side gap cases, against the baseline's 1 of 36. The certified repairs never do.
  This is a second, learnable gap.
- **Phase 27 ($22.24):** NOT_RECOMMENDED. The PENDING slip is about 2% (4 of 225). A status
  field removed it (0 of 225), but it broke correct rejection reports (23 of 45 turned into
  extra polls).
- **Plan:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_25-28.md`.
- **Budget:** $652.90 charged, $347.10 left.

## Earlier: Phases 18 and 19 (2026-09-23)

- **Phase 18:** Phase 17's certified policy (`dd62c857…`) ran once on the private promotion
  partition. **Verdict HARM**, final: 1 candidate episode of 18 failed C5, C6 and C8. The
  baseline had 0 failures.
- **Phase 19 ($0)** traced that failure to a **lab defect**, reproduced and fixed:
  - a request that had to open a new connection during a >1 s lab event-loop freeze was
    never sent, but its tick was counted;
  - the lab's clock ran one tick ahead of the world's, so a truthful citation failed C6;
  - the same drift hit 2 baseline episodes;
  - the freezes came, by strong inference, from an open **dashboard tab** polling two
    endpoints that parsed the whole store once a second (fixed).
- **The verdict still stands, and it does not hinge on the defect.** Rule 3 (fewer
  completions than the baseline) fires on two other cases. It is weak evidence at 3 trials
  per case, so held-out safety for `dd62c857…` is **unshown**. The
  promotion partition is spent for it.
- **Before any paid run:**
  - close the dashboard or check the loop
    (`artifacts/phase19-2026-09-23/diagnosis/loop_latency.py`);
  - start the simulator only via `scripts/start-simulator.sh`;
  - afterwards, run `scripts/experiments/check_clock_drift.py --worlds --since <date>`.
- **Next:** the experiment program in `docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md`, which starts with the Phase 20 development probe. The write-up is Phase 27, the last phase, not the next one.

## The honest bottom line — corrected by Phase 16 (2026-09-22)

**Read `docs/part2/PHASE17_RESULTS.md`, `PHASE17_EXPERIMENT.md` and `PHASE16_RESULTS.md` first.**

- **No generated policy has ever been ACCEPTED, and a completion study cannot produce one.**
  - `completion_study.py` never calls `commit_promotion`.
  - The only promotion path (`promotion.py`) needs the incumbent to *fail* a C1–C8 check,
    and a completion gap fails none.
  - The spec excludes completion-only sources from promotion.
  - The project's target is therefore a separately labelled **certified completion repair**
    (defined in the Phase 17 protocol). It is never called ACCEPTED.
- **The full loop has never produced a win:** 0 of 40 full studies reached
  `OBSERVED_IMPROVEMENT`. **All 40 ran on the old v1 Actor context**, before the citation fix.
  The default launcher still runs v1; Phase 17's runner passes v4 explicitly.
- **The Mechanic writes the fix in ~16% of studies** (5 of 31 first proposals; 4 of 15 on the
  closest setup). It runs at temperature 0, so the second slot repeated the first in 20 of 25
  studies: **one real draw per study, not two**. The pooled "16 of 100" was a text count
  mixing prompts; 15 were valid.
- **Validation is single-shot** and passes a working policy ~1 attempt in 3 (9 of 28).
  - "9 of 10 on clean batches" is the true gate figure.
  - "0 of 10 with an untriggered fault" is true by construction, not a finding.
- **The handoff's "$15–50, 4–14 studies" was 3–6× too optimistic.** Realistic: ~4% per study,
  ~25 studies, ~$55 at the conservative bound.
- **Phase 16 ($0)** built:
  - an in-study evidence re-read;
  - the Phase 17 runner, hardened by two adversarial review rounds;
  - a code freeze and pins;
  - a backup of everything (branch `backup/part2-2026-09-22`, plus
    `~/FaultLab_Backups/2026-09-22-pre-phase16/`).
- **Phase 17 (2026-09-23, $24.29) produced the first certified completion repair**:
  - it came on attempt 9 of a fresh full-loop run;
  - the policy is new (`dd62c857…`), and it repaired `notification-2` and `notification-3`
    on a batch with no violation and no untriggered fault;
  - a different generated repair was correctly rejected for breaking refusal handling;
  - it is **not** ACCEPTED, and Phase 17 is closed;
  - see `docs/part2/PHASE17_RESULTS.md`.

## Hard rules — these are not negotiable

- Never weaken C1–C8, `assess_pairs`, or any threshold. Never exclude a case. Never resample
  or "repeat until lucky". Never fabricate promotion. Never rewrite an original report.
  Never put protected/private truth into a model's input.
- **The untriggered-fault channel stays fatal by design.** It costs ~half the scored
  replays, which makes it tempting. Tolerating it would weaken the gate.
- Secrets live in the root `.env`, loaded by the backend. Never print, commit, or copy them;
  never put provider credentials in frontend code or `VITE_` vars.
- Preserve all negative results. Closed phases are closed — do not resume or re-tune them.
- Aria stays off. No deployment, no public push, no paid overages.

## Before any paid run

1. `./.venv/bin/python scripts/experiments/check_ingestion_health.py` — read-only, $0.
   Phase 12 burned $8.15 and 28 attempts because W&B Weave ingestion had silently degraded.
2. **Restart both services deliberately.** Phase 15 nearly measured the wrong code: the
   backend had been running since the previous day under `--reload`, and the runner drives
   it over HTTP, so *that* process builds the client. Use `scripts/start-simulator.sh` and
   the live (non-reload) backend launcher with the phase's settings file, then confirm
   `/api/config/status` shows the right models and `active_campaign_id: null`.
3. **Declare the protocol and read-out in writing, then adversarially review it before
   spending.** This has caught a read-out bug or worse every single time it has been run.
   For Phase 15 it returned "needs changes" on all four lenses and caught a false integrity
   claim, an undeclared nuisance parameter dominating the headline, a missing power
   calculation, a circuit breaker that would have aborted the run, and two latent runner
   defects that silently deleted verdicts the gate had already reached.

## Reporting rules earned the hard way

- **Quote the untriggered-fault rate beside any gate-acceptance headline.** Since Phase 11 a
  "pass" largely means all 36 fault-bearing episodes fired. That nuisance moved 2.1× between
  two compared phases and alone swings the expected headline from 0.63 to 0.37.
- **Never write "zero quality rejections" again.** It was true through Phase 13; Phase 15
  had 1 of 20 on a clean batch. Pooled it is 1 of 40 against Phase 10's 8 of 13.
- Report a shortfall as a shortfall. Never re-declare a read-out after seeing results.
- Never report the test suite as unconditionally green: one intermittent failure
  (`...reservation_released[untriggered]`, ~1 in 8 runs) is unexplained since Phase 10.

## Two store queries that produced wrong public claims from me

1. **Events live in their own `events` table** (`episode_id, seq, payload`), not in `records`
   with `kind='events'`; `type` is inside the JSON payload. Querying `records` returns 0 and
   looks exactly like "the feature never fired".
2. **`error_type` on a `completion_studies` record** is written by
   `completion_study._execute`'s own handler around `execute_slots`, so it names a failure
   *inside* episode execution, not in the runner's polling.

## Budget

**$465.24 conservatively charged, $534.76 remaining** of a shared $1,000 ceiling that began
at Phase 2 and does not reset. Phase 16 $0; Phase 17 $24.29; Phase 18 $4.22; Phase 19 $0; Phase 20 $18.77; Phase 21 $22.22 (now $506.23 charged, $493.77 left). The ledger rows actually sum to $436.45 (the
Phase 6 probe was counted twice); the higher figure is carried. Actual billed dollars are unavailable, not zero. A 30-attempt
replay run costs ~$97. Phase 14 cost $0 and produced more than most paid phases.

## Verification state

692 backend tests after Phase 19 (2026-09-23); 124 frontend tests, production build and three browser fixtures as last recorded (not re-run since; the frontend is unchanged).
`scorer_hash` and `actor_prompt_hash` verified identical to all 36 stored configurations.
`algorithm_hash`/`runtime_hash`/`configuration_hash` have moved since Phase 13 — declared,
not discovered. `checks.py` has never been opened.

## Reading order

1. This file.
2. `CLAUDE.md` — current truth, one bullet per finding.
3. `memory/context/next-phase.md` — the recommended next work.
4. `memory/context/pitfalls-and-decisions.md` — 85 numbered items; every one is a mistake
   already made and investigated. Read before proposing anything.
5. `memory/context/runtime-and-evidence.md` — services, per-phase evidence, cost ledger.
6. `docs/part2/PHASE19_RESULTS.md`, `PHASE18_RESULTS.md`, `PHASE17_RESULTS.md`, `PHASE16_RESULTS.md` and `PHASE17_EXPERIMENT.md`, then `PHASE15_RESULTS.md`, then `PHASE14`, `PHASE13`, `PHASE11`, `PHASE10`,
   `PHASE9`, `PHASE7`, `PHASE6`, `PHASE5` results.
