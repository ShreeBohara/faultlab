# Recommended next phase — Phase 16: run the full loop and try to get a policy ACCEPTED

Written after Phase 15. Read `docs/part2/PHASE15_RESULTS.md` first, then `PHASE14_RESULTS.md`.

## FIRST, BEFORE SPENDING ANYTHING

```bash
./.venv/bin/python scripts/experiments/check_ingestion_health.py
```

Read-only, $0. Phase 12 burned 28 attempts and $8.15 because W&B Weave ingestion had
silently degraded to 31% per-episode. It was 0.0% before Phase 15 and the run worked.

**Also restart both services deliberately before any paid run.** Phase 15 nearly measured the
wrong code: the backend had been running since the previous day, under `--reload`, and the
runner drives it over HTTP — so *that* process builds the `WorldClient`. Use
`scripts/start-simulator.sh` and the live (non-reload) backend launcher with the phase's
settings file, then verify `/api/config/status` shows the right models and
`active_campaign_id: null`.

## Where the project is

- **The declared read-out has been reached and it is significant.** Phase 15: **9 of 20
  scored accepted, Fisher p = 0.005** vs Phase 10's 0 of 13. Replicates Phase 13 (p = 1.00).
- **The number that isolates the gate:** of scored replays with **zero invalid trials, 9 of
  10 were accepted; with an invalid trial, 0 of 10.** When the batch is clean the gate
  certifies this repair 9 times in 10.
- **Always quote the untriggered-fault rate beside the headline** — 2.02% in Phase 15,
  1.28% in Phase 10, 2.75% in Phase 13. The headline substantially tracks it.
- **Quality rejection is near-eliminated but no longer zero**: 1 of 20 in Phase 15, 1 of 40
  pooled, against Phase 10's 8 of 13.
- **Nothing has been promoted.** Replay mode cannot accept a policy.

## The recommended next phase: RUN THE FULL LOOP

**Not the evidence channel.** That was the recommendation until 2026-09-22, when a direct
measurement changed the picture. See the "READ THIS FIRST" section of `CLAUDE.md`.

**The Mechanic emits the working repair ~16% of the time** (16 of 100 `mechanic_outputs`,
all at the correct hook; Phase 9 alone 6 of 44 = 13.6%). The project's carried belief that it
"never" does came from a six-proposal sample, where zero hits has probability 0.35 at that
rate. Phases 6–8 were spent explaining a non-event.

Meanwhile everything downstream is now fixed and measured:

| | state |
|---|---|
| Mechanic emits the step | ~16% per proposal, 2 slots per study |
| source gate | works |
| validation on a clean batch | **accepts 9 of 10** |
| lab control path | **closed** (Phase 14, 0 of 28) |
| Actor transport | closed (Phase 13) |
| citation corruption | closed (Phase 11) |
| evidence channel | 29% of attempts — a real cost, but survivable by retrying the study |

**And the full loop has not been run since Phase 9.** The store holds 126 replay studies
against 40 full-loop studies, and every phase from 10 to 15 replayed the same known policy.

**So: run full completion studies until a policy is ACCEPTED.** Rough arithmetic, to be
verified before spending: 4–14 studies, **$15–50**. That is the cheapest untried path to the
thing this project was built to demonstrate, and it is affordable many times over within the
$563.27 remaining.

**Verify before committing budget:**
1. Re-derive the step rate for the *current* brief and model — the 16% pools campaigns that
   ran under earlier briefs. A quick read-only query over `mechanic_outputs` filtered to
   recent campaigns will do it, and costs nothing.
2. Confirm a step-containing candidate still passes the source gate at a useful rate.
3. Then declare the protocol, review it adversarially, and run.

**If it works, the project has its result.** If the step rate collapses under the current
brief, that is itself the finding, and it is the one Phases 6–8 were actually looking for.

## The loss channels, for reference

| channel | Phase 13 | Phase 15 | status |
|---|---:|---:|---|
| lab control path | 11 of 30 | **0 of 28** | closed (Phase 14) |
| Actor transport | fatal on final turn | 0 fatal | closed (Phase 13) |
| citation corruption | 8 of 13 quality rejections | 1 of 20 | near-closed (Phase 11) |
| evidence / Weave | 6 of 30 | 8 of 28 (29%) | **untouched** |
| untriggered fault | — | 10 of 20 scored | **deliberately fatal, not a defect** |

The evidence channel remains the only unfixed defect, and is worth doing *after* the loop
run — it raises throughput but proves nothing on its own.

**Do not make the untriggered-fault channel non-fatal.** It costs half the scored replays,
which is tempting. Tolerating an untriggered fault would weaken the gate.

## Method notes that paid for themselves

- **Run the four-lens pre-run review before every paid run.** For Phase 15 it returned
  `RUN_WITH_CHANGES` on all four lenses and caught a false `algorithm_hash` claim, an
  undeclared nuisance parameter dominating the read-out, an undeclared stronger figure, a
  missing power calculation, an optimistic yield, a circuit breaker that would have aborted
  the run, and two latent runner defects that silently deleted verdicts the gate had already
  reached.
- **Pre-declare the decomposition, not just the headline.** Phase 15's best result — the
  conditional 9 of 10 — is quotable only because it was declared in advance.
- **Two store queries to get right.** Events live in their own `events` table, not in
  `records` with `kind='events'`. And `error_type` on a `completion_studies` record is
  written by `completion_study._execute`'s own handler, so it names a failure *inside*
  episode execution.

## Budget

**$436.73 conservatively charged, $563.27 remaining** of the shared $1,000. Phase 15 cost
$97.33; Phase 14 cost $0. A 30-attempt replay run is ~$97.
