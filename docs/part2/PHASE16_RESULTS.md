# Phase 16 results — September 22, 2026

**Free phase. No provider call, no W&B call, $0.** Phase 16 checked the handoff's
recommended next step before spending anything, found that it could not work as written,
and built the smallest set of changes that let a full-loop run succeed honestly. The paid
attempt is Phase 17, declared separately in `PHASE17_EXPERIMENT.md`.

Evidence: `artifacts/phase16-2026-09-22/` (gate freeze before and after, verbatim pre-edit
copies of every edited file with `SHA256SUMS`, the frozen Phase 17 settings file).

## 1. What the audit found (read-only, over a snapshot of the store)

Twelve read-only agents checked the handoff's claims against a consistent copy of
`artifacts/lab.sqlite3` and the code. Each decision-relevant number was re-derived by an
independent second agent. A second round of eight agents then mapped promotion, contracts,
the launch path, evidence retry and tests.

**The handoff recommended "run full completion studies until a policy is ACCEPTED, 4–14
studies, $15–50." Three things make that wrong:**

1. **A completion study can never write ACCEPTED.** `completion_study.py` never calls
   `commit_promotion` (module docstring; comment at the validation boundary). The only caller
   is `learning.py`, and its predicate (`promotion.py:16`) requires the incumbent to *fail* a
   C1–C8 check 3 of 3 times. A completion gap passes every check. The spec also says so
   outright: a completion-only source "does not qualify in this build"
   (`FaultLab_Specs/.../evaluation-plan.md:104`; `experiment-protocol.md:92-95,130-131`).
2. **Launched the usual way, a full study runs on the old v1 Actor context.**
   `actor_context_protocol or ACTOR_CONTEXT_PROTOCOL_V1`. `run-completion-study.sh` and
   `run_replication.py` cannot send anything else. All 40 full studies ever run used v1. The
   known-good policy was accepted in 0 of 26 v1 replays and 17 of 100 v4 replays.
3. **The cost estimate was 3–6× too optimistic.**
   - The Mechanic runs at temperature 0. Its second slot repeated the first policy in 20 of 25
     studies and added the step 0 of 22 times, so a study is one draw, not two.
   - Validation runs once per study. A working policy passes about 1 attempt in 3 (9 of 28),
     not the 9 in 10 that describes clean batches only.
   - Corrected: roughly 4% per study, about 25 studies to the first success, and 55–70 for a
     90% chance.

**Other corrections to carried claims:**

| claim | correction |
|---|---|
| "16 of 100 contain the step, all at the correct hook" | 16 text matches, 15 valid steps; the 16th has its `steps` key corrupted to `极速steps`. The pool mixes prompts: 22 of the 100 are diagnoses. Study-level: **5 of 31 first proposals (16%)**; closest to the current setup 4 of 15 (27%, CI 11–52%) |
| "the source gate works" | 1 of 5 step candidates qualified, all under v1. **3 of the 4 failures** were a candidate-arm C6 citation error (the Actor cited a call id as an evidence id), which v4 removed; the 4th was INCOMPLETE because one candidate trial's fault never fired. The one that qualified (T15) later failed validation on C6. **Unmeasured under v4.** (A first version of this row said "every one of the 4"; the review caught it.) |
| Phase 15 "0 of 10 accepted with an untriggered fault" | **True by construction** (`assess_pairs` returns INCOMPLETE for any invalid trial), so it is not a finding. The informative figure is 9 of 10 on clean batches (CI 0.60–0.98) |
| Phase 15 untriggered rate 2.02% | Denominator included the 6 no-fault healthy episodes. **2.4–2.6% per fault-bearing episode** (20/759 = 2.64%), so P(all 36 fire) ≈ 0.38–0.42, not 0.48 |
| "Phases 6–8 explained a non-event" | Half right. V4's zero in a few draws was unremarkable. V3.1's zeros were structural: it emitted the same bytes at temperature 0. A ~2× effect of the `task_outcome` presentation (T 3/14 vs C 1/11) is still plausible |
| Every untriggered fault | **73 of 73** are the same Actor lapse: it polls the status of a confirmation it never sent, sees UNKNOWN, and gives up without sending. ~3% of notification-fault episodes, even across arms |
| `EvidenceDenied` | **21 of 21** are a lab-error episode (provider HTTP failure) that the evidence gateway correctly refuses. None was a real evidence mismatch |
| budget ledger | Rows sum to $436.45, not $436.73. The $0.28 is the Phase 6 probe counted twice (safe direction). Every figure is a per-call **upper bound**; token counts at list price suggest the real bill is roughly 10× lower (unverified) |
| repository safety | Nothing from Part 2 was in git: 66 modified plus 107 untracked files, including `completion_study.py`. `artifacts/` (3.6 GB) had no backup |

## 2. Decision on what "success" means

The user delegated this. I first proposed wiring the completion path to ACCEPTED, and then
withdrew that after reading the code and spec. ACCEPTED in this codebase means source
qualification **plus an active challenge plus an independent promotion-partition batch**.
Mapping a completion study's `OBSERVED_IMPROVEMENT` to ACCEPTED would have set a lower bar
for completion repairs, contradicted explicit spec text, and made the policy eligible for the
single-shot sealed final audit, which runs the Actor on v1.

**Declared instead: a separately labelled "certified completion repair"** (full definition in
`PHASE17_EXPERIMENT.md`). It needs a fresh full study to reach `OBSERVED_IMPROVEMENT` under
the unchanged `assess_pairs`. It *also* needs at least two more candidate completions than
baseline completions (`L − B0 ≥ 2`) on one validation case other than the source case and
the healthy control. The second requirement exists because the unchanged gate can pass on
the source case alone: `notification-2` is in the validation set and the baseline was
selected to fail it. It is stricter, not looser. It was raised from "≥ 1" in review round 1,
because a single baseline lapse could otherwise supply the gain.

Nothing is called ACCEPTED, no pointer moves, and nothing is activated. A route from a
certified repair to ACCEPTED would be its own later phase, declared before its data exists.

## 3. What was built

| change | where | why |
|---|---|---|
| Local backup | branch `backup/part2-2026-09-22` (`e762c30`) plus `~/FaultLab_Backups/2026-09-22-pre-phase16/` | nothing from Part 2 was preserved anywhere. The branch is a snapshot commit made without touching the working tree or `main`. The folder holds a git bundle, a full `artifacts/` copy, the store copied via the SQLite backup API (`quick_check` ok), the specs and a README |
| In-study evidence re-read | `completion_study.py` (`verified_evidence`), `evidence.py` (`retry` accepts the study's context and stop flag), `worker.py` (`ensure_running`, `_initialized`) | the evidence channel lost 8 of 28 Phase 15 attempts. See below for exactly what it does |
| Health check | `check_ingestion_health.py` | every episode whose first read failed now counts once, whatever the re-read did, so the guard cannot report a failing channel as healthy (pitfall 48) |
| Gate freeze | `scripts/experiments/gate_freeze.py` | stdlib-only fingerprint of `assess_pairs` and everything it depends on. It reproduces Phase 15's recorded `783e8e58…` |
| Expected configuration | `scripts/experiments/expected_configuration.py` | the backend's own `frozen_configuration` applied to the frozen settings file, giving the value the Phase 17 runner pins |
| Phase 17 runner | `scripts/experiments/run_full_loop.py` | based on the Phase 15 runner, keeping all of its review fixes, then hardened by two review rounds. See the protocol |
| Phase 17 read-outs | `scripts/experiments/phase17_readouts.py` | S3–S5 computed exactly as declared, written before any data. On Phase 15's studies it reproduces 20/759 untriggered and 7 first-read failures in 914 reads |

**What the in-study re-read does:**
- it fires only on a read that failed with DEADLINE or TRANSPORT;
- it restarts a telemetry worker that is dead, or alive but never initialized;
- it re-uploads the saved local trace once and reads once more;
- it is blind to arm, outcome and stage, and never retries an integrity failure;
- the first failure and its result are kept in the study record, because a successful
  re-read overwrites the ingestion row.

**Deliberately not changed:** `assess_pairs`, `case_manifest`, `planned_slots`, the manifest
hash, `checks.py`, `promotion.py`, the Mechanic, its prompt, its temperature and its two
slots, the default Actor context (Phase 17 passes v4 explicitly), and the LAB_ERROR →
EvidenceDenied route. The last one is a known, small channel; fixing it touches Mechanic
input and would add a variable.

## 4. Integrity

`artifacts/phase16-2026-09-22/gate-freeze-before.json` against `gate-freeze-after.json`
(sha256 `96dc32a05d7e715c9752aa7837f1593c967efc02df975a332dea3e5f45faa20f`). The after file
was written after the last code edit of review round 1.

| | before → after |
|---|---|
| `assess_pairs` text sha256 | `783e8e58f91992f3…` → **identical** (text and AST) |
| `case_manifest`, `planned_slots`, `queue_completion_study`, `valid_trial`, `summarize`, `score`, `promotion_decision`, `commit_promotion`, `TrialResult`, `EpisodeRunner.run`, Mechanic, `summarize_evidence`, `trial_outcomes`, `runtime_contract` | **identical**. Some line numbers moved; text and AST did not |
| changed functions | `_execute` (the re-read call site), `EvidenceGateway.retry`, `WeaveWorker` — exactly the declared three |
| `scorer_hash`, `contract_hash`, `adapter_hash`, `source_hash`, `actor_prompt_hash`, `interpreter_hash`, `service_hash`, `dependency_lock_hash` | **unchanged** |
| `algorithm_hash` | `c59cacf5…` → `8d92e0c5b7dc5c1f…` (declared) |
| `runtime_hash` | `b1c765b4…` → `485c5e1243407367…` (declared) |
| expected `configuration_hash` | `c4169ee49deb7fb2…`. Rebuilding Phase 15's stored `21df22de…` with only these two code hashes swapped gives exactly this value, so every settings-derived field is identical to Phase 15 |

The recomputed pre-change fingerprints equal the stored Phase 15 configuration, so the code
before Phase 16 was byte-identical to what Phase 15 ran. "`checks.py` never opened" means no
person or agent read it; `gate_freeze.py` and the backend hash its bytes.

## 5. Verification

- **Backend suite before any edit:** 594 passed (the handoff said 592).
- **New tests:**
  - 17 for the re-read and v4 (`tests/lab/test_completion_evidence_reread.py`);
  - 36 for the runner against a scripted fake backend and a throwaway store, whose budget
    route behaves exactly like the real one (`tests/experiments/test_run_full_loop.py`).
- **What the new tests cover:**
  - a lost trace at four positions is recovered, with identical trials, verdicts and Mechanic
    calls;
  - a TRANSPORT failure from a dead worker recovers after a restart;
  - there is at most one re-read, after which the original failure is kept;
  - a timed-out or broken re-read is labelled;
  - no re-read happens for REJECTED, NOT_AUTHORIZED, STOPPED or no-ingestion failures;
  - a tampered re-upload is an integrity failure;
  - a stop during a re-read interrupts;
  - `ensure_running` restarts only a dead or half-started worker;
  - the **first end-to-end completion study under v4**, with every Actor turn stamped v4;
  - the default is still v1;
  - the certification rule, and all 17 pre-Phase-17 improving assessments pinned by id;
  - checkpoint, resume and the approval gate, including after a hard kill;
  - a signal leaves the study running and resume recovers it;
  - an interrupted start is adopted;
  - a finished outcome survives a failed re-read, and a failed post-finish check
    uncertifies;
  - a ledger-less campaign costs $0 while a real ledger with no bound aborts;
  - the configuration, Aria, project and process pins;
  - the spend guard, and the breaker at exactly 5;
  - the freeze and pin refusals, and reconciliation.
- **Mistakes of mine, recorded:**
  - **The breaker test.** The first runner tests had a breaker test written for a threshold
    of 4, and I raised the default to 5 afterwards. The full-suite run I first reported as
    "622 passed" had loaded the old version, so the file on disk was red. Round 1 caught it.
  - **A hanging test.** While fixing round 2's findings, one new test hung because my fake
    backend never became idle on the adoption path. The fake is fixed, and every runner test
    now caps idle waits at 2 seconds.
- **Full suite after all round-2 changes:** see the final line of this section.
- **Still unexplained:** the known intermittent `[untriggered]` failure (~1 in 8). It did not
  occur in the runs recorded here, which does not mean it is fixed.
