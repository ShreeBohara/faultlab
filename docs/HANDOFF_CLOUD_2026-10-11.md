# Handoff to the cloud session (2026-10-11, ~17:20 UTC)

The owner's local plan limit was about to end, so the working Claude session moved to a Claude Code
cloud session. This file is what that session (and any later local session) must know beyond the
code and git history. It wins over older handoff files where they conflict; `CURRENT_STATUS.md`
remains the ledger of record.

## Where things are

| Thing | Where | Reachable from the cloud? |
|---|---|---|
| Source of truth | GitHub `main` (`https://github.com/ShreeBohara/faultlab`) | yes |
| Working clone on the owner's Mac | `~/FaultLab/faultlab`, branch `backup/part2-2026-09-22` (GitHub `main` is fast-forwarded from it) | no |
| Archive folder (never checkout/commit/reset/stash/clean there) | `~/Desktop/Coreweave_AGI_Hackthon/faultlab` | no |
| Paid-run folders | `~/FaultLab_Runs/<date>/...` (the Claude Actor screen: `~/FaultLab_Runs/2026-10-11/claude-actor-screen`) | no |
| Backups | `~/FaultLab_Backups/...` | no |
| Machine-wide spend ledger | `~/.faultlab/spend-ledger.sqlite3` | no |
| Credentials | `~/FaultLab/faultlab/.env` only, placed by the owner | no, and never copied anywhere |
| The plan | `~/Desktop/Coreweave_AGI_Hackthon/FaultLab_Plan_2026-10-10/` (7 stages, 62 phases, 6 gates); the Stage 1 table is repeated below | no |

## Standing rules (unchanged)

- Never print, copy, paste or commit credentials; keys live only in the owner's `.env`.
- Never open `backend/app/referee/checks.py`, `artifacts/heldout2/`, `audit/promotion.json`,
  `audit/final-audit*.json`. Never tune on private or held-out data. Never weaken C1 to C8, gates
  or thresholds. Never delete `artifacts/` or the runs folders.
- Never run two agents on the repo at once. Never edit `backend/app` while a paid run is going.
- Paid runs need a declaration with a sha256, caps, stop rules and a ledger entry; the cloud session
  cannot run paid studies (no key, no local lab), so it does offline work only.
- Secret-scan before every commit; commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Plain, short explanations for the owner; plan by phases, not dates; evidence over narrative; no
  partial-completion claims.

## State at the move

- Stage 0 is done (0.1 to 0.8, 0.7 optional). Stage 1 has first cuts of 1.1, 1.2, 1.4, 1.8, 1.9 and
  1.10 (see `docs/v2/README.md`). The Claude Actor screen phase A is written up in
  `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`.
- **Phase B of the screen is running unattended on the Mac** (36 studies, nine rounds of four models,
  declared in the run folder's `DECLARATION.phase-b.json`, sha256
  `e56521f9fc4c6bc64979410f77faf7ecc4f4b0b6582f08843d28395689af6286`; about 22 minutes per round;
  expected to end around 19:45 UTC on 2026-10-11). A wrap-up script (`phase_b_wrapup.sh`, parented
  to launchd) waits for the loop, runs both clock-drift checks per store, regenerates the
  leaderboard, runs the per-run and pooled reports, backs the run folder up, secret-scans, and
  **commits the read-outs to GitHub `main` under `artifacts/claude-actor-screen-2026-10-11/phase-b/`**
  through a temporary worktree. If that folder has not appeared on `main` by 21:00 UTC, the owner
  has to look at `~/FaultLab_Runs/2026-10-11/claude-actor-screen/phase_b_wrapup.log` on the Mac.
- Measured cost so far: phase A $2.70; phase B about $0.60 per round of four (Opus is most of it).
  The owner authorized spending the Claude promotional credit (about $200, expiring 2026-10-16) at
  Claude's judgment; the lab's monthly cap for these driver processes was raised to 400 by that
  authorization (the ledger records every reservation).

## What the cloud session does next

1. Pull `main` now and then; when `artifacts/claude-actor-screen-2026-10-11/phase-b/` lands, write
   the phase B findings with the pre-registered read-outs from the declaration, nothing else:
   per model, violations and completions out of 180 with 95% Wilson intervals, per case out of 30;
   per model, the fraction of stale-read trials where the fault could not fire; the three phase-A
   observations each marked supported / not supported / mixed; the two-sided Fisher test per Claude
   model against the pooled DeepSeek control (p below 0.017 counts as notable after Bonferroni);
   measured cost per model. `pooled.txt`/`pooled.json` and `report.txt` carry the numbers,
   `leaderboard.md` the intervals, `clock-drift.json` the after-run checks (every study must show
   `drifted: 0` and exit 0 for the read-out to count; otherwise report the affected studies as
   excluded, with the reason). Put the write-up in `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`
   (a "Phase B" section) and add the ledger line to `CURRENT_STATUS.md` from
   `LEDGER.phase-b.auto.json` (measured) plus the declaration's reserved bounds.
2. Continue Stage 1 offline. Next in order of value: **1.3 the task-pack interface** (design notes
   below), then 1.5 (trial worker, scheduler, typed store), 1.6 (adapter interface and registry),
   1.7 (CLI, pytest plugin, CI action), the rest of 1.8/1.9/1.10, 1.11, 1.12. Run
   `./scripts/setup.sh --backend-only` then `./scripts/test.sh backend` (Python 3.12); the v2 tests
   are `backend/tests/v2` (75 passed, 1 skipped at the move).
3. Keep the commit discipline: small commits, tests with each piece, docs in `docs/v2/`, and push to
   `main` (the owner authorized publishing on 2026-10-11; see `PUBLISHING.md`).

### 1.3 design notes (worked out before the move, not yet coded)

- `faultlab/packs/base.py`: `Scenario` (scenario_id, label, description, fixture_id, the kernel-form
  `fault_spec`, a derived v2 `FaultSchedule` using the same placement mapping as
  `faultlab/evidence/legacy.py`, expected_class), `PropertySpec` (property_id, title, family,
  severity; families and severities as in `CHECK_FAMILIES`), `PropertySet` (properties plus the
  pinned sha256 of the checker file, computed from bytes, never by reading it), and `TaskPack`
  (pack_id, version, handler factory, business router, intent and report models, effectsafe
  `ToolContract` per tool, hooks, fixtures, scenarios, properties, optional diagnostics;
  `manifest()` as declarative JSON, `digest()` over it, `plan(scenario_id, agent, environment,
  protocol_version, caps)` building a `TrialPlan`).
- `faultlab/packs/orders/pack.py`: the orders instance. Tools: `get_order` and
  `get_operation_status` are reads; `update_order` is a keyed write (client key in the payload,
  mismatch is a conflict, async commit, status via `get_operation_status`, VERSION_CONFLICT and
  IDENTITY_CONFLICT prove no effect); `send_confirmation` is a keyed write committed on ack.
  Hooks: the legacy four. Scenarios: the six development cases, copied from
  `audit/development.json` (public development split; promotion and final-audit stay private).
  Properties: C1 to C8 with the public one-liners from `PUBLIC_INVARIANTS` in
  `backend/app/agents/explorer.py`.
- `faultlab/packs/registry.py` and a `packs` subcommand in `faultlab/__main__.py`.
- `backend/tests/v2/test_pack_conformance.py`, parameterized over the registry: manifest
  round-trip and stable digest; handler pack_id and fixtures agree; every scenario's fixture is
  known, its fault_spec passes `validate_schedule`, and the kernel creates a world for it; every
  placement names a declared tool; hooks and property ids unique; keyed writes name a read tool
  for status; `plan()` yields a valid `TrialPlan`. Orders parity: scenarios equal the legacy
  development manifest, hooks equal the legacy `HOOKS`, tools equal the legacy `Tool` literal,
  the report model's JSON schema equals the legacy `TaskReport`'s, the properties digest equals
  the sha256 of `backend/app/referee/checks.py` computed in the test.

## Progress log of the cloud session (2026-10-11, from ~17:15 UTC)

Each item is a commit on `main` with its tests and a page in `docs/v2/`; the v2 suite went from
75 to 114 passed. Nothing paid ran. The phase B artifacts had not appeared on `main` while this
was written (checked repeatedly); the phase B write-up and ledger line are still open.

- **1.3** `TaskPack` interface, the orders declaration (public development split, legacy hooks and
  tools, C1 to C8 pinned to the checker's sha256 without reading it), registry, `faultlab packs`,
  conformance tests with orders parity (`PACKS.md`).
- **1.5** `TrialStore`, scheduler with batch-cap admission, `TrialWorker`, `TrialSession` on
  effectsafe, in-process `KernelTransport` where a lost reply is decided by the declared delay, not
  raced (`LAB.md`). The legacy orders checks run behind the v2 `Referee` protocol through
  `faultlab/referee/legacy.py`, called as a black box and refused unless their digest is the one the
  plan pinned. The session refuses replies that do not bind to the trial's identities (the legacy
  broker's rule, ported). effectsafe: a key already in the payload is kept; `Journal.observe` folds
  a status read into the write it reports on.
- **1.6 (first cut)** adapter interface and registry, `reference-orders` (the legacy B1 control
  on the session; passes C1 to C8 on every development scenario), `faultlab run` and
  `faultlab adapters` (`ADAPTERS.md`). Then, on the owner's choice, `model-actor`: the legacy
  Actor prompt loop on the session (same prompt hash, same turn message, v4 indexed evidence,
  same retry and final-turn rules), tested with a scripted provider; a live run is
  `faultlab run --adapter model-actor --model <provider:model> --execute-live --dollars <bound>`
  on the Mac, under a declaration. Not done: native smolagents and local `decide()` adapters, and
  recovery policies through the session.
- **1.7 (first cut)** the pytest plugin (`faultlab_lab`, `assert_clean`), a CI job that runs every
  orders scenario twice with the reference adapter and the fixed checks and fails on any problem,
  `faultlab run --bundle` (`TESTING.md`).
- **1.8 (second part)** replay of recorded inputs in a fresh world with divergence stop and cut-point
  continuation (`EVIDENCE.md`). A `faultlab run` bundle reads into the bench leaderboard.
- Repair: `backend/tests/v2/test_bundles.py` shared its basename with the incident-evidence module
  and broke collection of the full backend suite (`./scripts/test.sh backend` failed at collection
  on `main` before this session); renamed to `test_envelope_bundles.py`.
- Full backend suite in the cloud container (after 1.8): 2,490 passed, 9 skipped, 11 failed in
  44 minutes. All 11 are the native smolagents child-process path (`tests/native_agents`, the
  native incident-evidence cases): the child answers `NATIVE_AGENT_EOF` instead of running. The
  same tests fail the same way on the pre-session commit `228e5ee` in this container, so it is the
  container, not this session's commits; GitHub CI (ubuntu) and the Mac are the reference for
  those. The v2 suite is 120 passed, 1 skipped (plus 3 driver tests under `tests/experiments`).

- **Credit plan**: the owner decided on 2026-10-11 to spend the whole promotional credit. The
  plan, declarations and read-outs are in `docs/CLAUDE_CREDIT_PLAN_2026-10-11.md` (piece C: the
  screen with Fable 5.1; D: completion studies with Sonnet Actor and Opus Mechanic; E: Opus
  Actor until the credit is spent). `baseline_screen.py --study completion` queues a completion
  study with the same declaration, caps and stop rules as a baseline study (offline-tested watch
  loop). The launch is local, after the phase B read-out, before 2026-10-16.

- **Phase B did not publish, and the loop ended early.** The owner's console had a $20 monthly
  spend limit; it tripped at 18:49 UTC (Anthropic's email), the API refused every Claude call
  until the owner raised the limit to $230 around 19:00, and the loop ended with 30 of 36 study
  folders (b7 Opus never ran, b8 Haiku interrupted, rounds 8 and 9 never started). The wrap-up
  ran at 18:56 UTC, passed the drift checks, leaderboard, reports, secret scan and backup, and
  logged "PUBLISHED to GitHub main: 746fd8f", but git answered "Everything up-to-date": nothing
  was committed, because `artifacts/` is in `.gitignore` and the script's `git add` was not
  `-f` (every earlier evidence folder on `main` was force-added). The read-outs are intact in
  `~/FaultLab_Runs/2026-10-11/claude-actor-screen/`. To publish by hand on the Mac: in the
  wrap-up's worktree (`git worktree list` in the clone) or the clone itself, copy or find
  `artifacts/claude-actor-screen-2026-10-11/phase-b/`, then `git add -f` that folder, commit and
  push. Done by the owner on 2026-10-12 (`ea3776a`). The Phase B section of
  `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md` and the ledger line in `CURRENT_STATUS.md` are written
  from the clean studies (28 of 30; `b7-claude-opus-5-5` and `b8-claude-haiku-5-5` excluded as
  errors). Fix the wrap-up script's add to `git add -f` before phase C. The earlier estimate of
  "$0.60 per round of four" was wrong: a round measures about $2.45, and the console's $20.14
  matches the lab's accounting.

Still open from the Stage 1 list: the rest of 1.6 and 1.7 (above), the rest of 1.9 (free-text
extraction, calibration by fault phase), 1.10 (a core suite under five minutes; the full backend
suite is 3,840 tests, 1,085 of them under `tests/lab`), 1.11 (exporters, Weave optional), 1.12.

## For the next local session on the Mac

- Fast-forward the clone: `git -C ~/FaultLab/faultlab fetch origin && git -C ~/FaultLab/faultlab merge --ff-only origin/main`
  (the local branch is an ancestor of `main` unless someone committed locally).
- Confirm the wrap-up published (`phase_b_wrapup.log`), then update the run folder's `LEDGER.json`,
  `FINDINGS.md` and `SUMMARY.json` from the committed read-outs, and the memory index.
- Any further paid work (for example a declared Claude lab-loop probe) is a local decision with a
  fresh declaration.
