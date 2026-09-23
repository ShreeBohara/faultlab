# START HERE — FaultLab continuation handoff

Written 2026-09-22, after Phase 15. This file is the entry point. Read it fully before
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

## The honest bottom line, and it matters more than any individual phase result

**Read this before deciding what to work on.**

- **No generated policy has ever been ACCEPTED or promoted.** Not once, in 15 phases. Verify
  it yourself: 0 policy records with `decision == 'ACCEPTED'`.
- **The Mechanic DOES emit the one step that fixes the task, about one proposal in six.**
  This corrects the project's own long-standing claim. Measured 2026-09-22 over
  `mechanic_outputs` (n=100): **16 contain `retry_original_request`, 16.0%**, all at the
  correct hook `after_notification_response`; Phase 9 alone 6 of 44 = 13.6%. The carried
  belief that it "never" does came from a **six-proposal sample**, and at a 16% rate
  zero-in-six has probability **0.35** — an ordinary outcome. **Phases 6, 7 and 8 were spent
  explaining a non-event.** Re-derive the rate under the current brief and model before
  relying on it: the 16% pools older campaigns.
- **Phases 9–15 did not work on that.** They fixed measurement and infrastructure. That work
  is real and is finished, but it is not the goal.

**What Phases 9–15 did establish**, so it is not re-litigated:

| | result |
|---|---|
| Actor citation corruption (Phase 11) | fixed — fabricated IDs 3.43% → 0 in 370 episodes |
| Actor transport failures (Phase 13) | retried; survives on the final turn |
| Lab control path (Phase 14) | cause found in uvicorn's keep-alive close; fixed |
| Declared read-out (Phase 15) | reached at last: **9 of 20 accepted, p = 0.005** vs Phase 10's 0 of 13 |
| **What the gate actually does** | **on a clean batch it certifies the working repair 9 times in 10; with one untriggered fault, never** |

So: **the gate works, the harness works, and the Mechanic produces the repair about one
proposal in six — yet no policy has ever been accepted, because the full loop has not been
run since Phase 9.** The store holds 126 replay studies against 40 full-loop ones; every
phase from 10 to 15 replayed one already-known policy.

**That is the open problem, and it looks cheap.** Rough arithmetic, to be verified before
spending: 4–14 full completion studies, **$15–50**, against $563.27 remaining. See
`memory/context/next-phase.md`.

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

**$436.73 conservatively charged, $563.27 remaining** of a shared $1,000 ceiling that began
at Phase 2 and does not reset. Actual billed dollars are unavailable, not zero. A 30-attempt
replay run costs ~$97. Phase 14 cost $0 and produced more than most paid phases.

## Verification state

592 backend tests, 124 frontend tests, production build, three browser fixtures.
`scorer_hash` and `actor_prompt_hash` verified identical to all 36 stored configurations.
`algorithm_hash`/`runtime_hash`/`configuration_hash` have moved since Phase 13 — declared,
not discovered. `checks.py` has never been opened.

## Reading order

1. This file.
2. `CLAUDE.md` — current truth, one bullet per finding.
3. `memory/context/next-phase.md` — the recommended next work.
4. `memory/context/pitfalls-and-decisions.md` — 67 numbered items; every one is a mistake
   already made and investigated. Read before proposing anything.
5. `memory/context/runtime-and-evidence.md` — services, per-phase evidence, cost ledger.
6. `docs/part2/PHASE15_RESULTS.md`, then `PHASE14`, `PHASE13`, `PHASE11`, `PHASE10`,
   `PHASE9`, `PHASE7`, `PHASE6`, `PHASE5` results.
