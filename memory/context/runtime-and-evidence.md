# Runtime, evidence and budget

Snapshot: September 20, 2026, after Phase 4. Recheck live process state when starting.

## Workspace and running services

- App root: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
- Specs: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/FaultLab_Specs`.
- Git branch `main`, HEAD `cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe`. Latest implementation is substantially modified/untracked and has not been pushed. Phase 4 added `backend/app/agents/progress.py`, `backend/app/lab/context_study.py`, `frontend/src/contextStudy.ts`, `frontend/src/components/ContextStudyPanel.tsx`, `scripts/run-context-study.sh`, `scripts/experiments/summarize_context_study.py`, three test modules and `docs/part2/PHASE4_*.md`.
- Backend `http://127.0.0.1:8000`, simulator `http://127.0.0.1:8001`, frontend `http://127.0.0.1:5173/` were reachable; no campaign active. Do not open `frontend/index.html` as a file.
- `.venv/bin/python` is installed locally. Backend module commands run from `backend/` with `../.venv/bin/python`, or with `PYTHONPATH=backend` from root.
- `./scripts/test.sh` runs the integrated checks. See `docs/setup.md` and `docs/user-guide.md` for service commands. No provider calls are needed for startup/readiness/offline tests.

## Exact live settings at handoff

Non-secret overrides: `artifacts/phase4-2026-09-20/settings-phase4.json` (identical to the Phase 3 B2 file). Credentials stay in `.env`, loaded by backend settings. Actor `deepseek-ai/DeepSeek-V3.1`; Explorer and Mechanic `deepseek-ai/DeepSeek-V4-Pro-0813`. V4 thinking is disabled by its provider settings. A/B used Mechanic V3.1, preserved in `settings.json` beside it.

Confirmed W&B destination: **`shreetbohara-quinstreet/Faultlab`**, capital F. `shreetbohara-quinstreet/faultlab` in early conversation is not the current case-sensitive project spelling. GitHub is the public `ShreeBohara/faultlab` repository; verify existing origin before any separately requested push.

Caps: $400 per campaign, 6,000 calls, 204 million total tokens, 32,000 admitted input and 2,000 output tokens per request. One Actor episode: eight model turns, 18 HTTP attempts, 20 ticks, four wait cycles, 32 policy steps, 90 seconds. Provider request timeout 20 seconds, no automatic provider retry. One bounded schema-correction request is separately charged where supported. Business-tool transport retry is distinct from model-provider retry.

Configured price rates per million input/output tokens: V3.1 $0.55/$1.65; V4 $1.31/$3.96. Conservative bounds: V3.1 $0.0209/request, V4 $0.04984/request. Frozen protected reservation is 1,064 calls; the separate completion study additionally admits 484 worst-case requests and a context study 480. Rate/settings verification already existed for these executions; reverify pricing when changing models or rates.

To restore this exact local server configuration, only after confirming the existing backend is idle and stopped:

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend
../.venv/bin/python - <<'PY'
import json, os, pathlib, sys
overrides = json.loads(pathlib.Path('../artifacts/phase4-2026-09-20/settings-phase4.json').read_text())
os.environ.update(overrides)
os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'])
PY
```

This does not edit `.env` or make model calls. Avoid silently using launcher defaults with another model or confusing a new shell's settings with the running backend's overrides.

## Cumulative accounting

The shared $1,000 authorization began with Phase 2 and continues through Phase 3 and authorized follow-on work. It does not reset with a new agent, account, campaign or laptop. It is tracked across stores/probes; the application does not enforce an account-wide shared limiter.

| Scope | Model requests | Conservative charge | Known-token price estimate |
|---|---:|---:|---:|
| Phase 2 | 886 including four format probes | $18.92256 | $1.77595950 |
| Phase 3 A | 61 | $1.50642 | Included in Phase 3 below |
| Phase 3 B | 129 | $2.69610 | Included in Phase 3 below |
| Phase 3 B2 | 33 | $0.68970 | Included in Phase 3 below |
| Phase 3 total | 223 | $4.89222 | $0.52858505 |
| Phase 4 study 1 (`v2`) | 321 | $6.70890 | $0.59667135 |
| Phase 4 study 2 (`v3`) | 332 | $6.93880 | $0.63241200 |
| Phase 4 total | 653 | $13.64770 | $1.22908335 |
| Phase 5 5A (V4 Mechanic) | 81 | $1.75078 | Included in Phase 5 below |
| Phase 5 5B (V3.1 Mechanic) | 85 | $1.77650 | Included in Phase 5 below |
| Phase 5 total | 166 | $3.52728 | $0.34556115 |
| Phase 6 Part A probe | 8 | $0.28296 | $0.06381 |
| Phase 6 6A (V4, clarified brief) | 77 | $1.66718 | Included in Phase 6 below |
| Phase 6 6B (V3.1, clarified brief) | 36 | $0.75240 | Included in Phase 6 below |
| Phase 6 total | 121 | $2.70254 | $0.29338550 |
| Phase 7 Part A probe (non-scoring) | 8 | $0.28296 | $0.07384 |
| Phase 8 8A (V4, task_outcome) | 74 | $1.60448 | Included in Phase 8 below |
| Phase 8 8B (V3.1, task_outcome) | 101 | $2.11090 | Included in Phase 8 below |
| Phase 8 total | 175 | $3.71538 | $0.36308 to $0.86512 |
| Phase 9 replication (32 studies, 16/arm) | see manifest | $53.56838 | not separately reconciled |
| Phase 10 gate replays (26 attempts, 828 episodes) | see manifest | $93.82010 | not separately reconciled |
| Phase 11 citation fix (13 attempts, 370 episodes) | see manifests | $39.77270 | not separately reconciled |
| Phase 12 (aborted, external) | 28 attempts | $8.15 | — |
| Phase 13 health probe (1 replay) | see manifest | $4.70250 | not separately reconciled |
| Phase 13 gate replays (30 attempts, 849 episodes) | see manifest | $91.41660 | not separately reconciled |
| Phase 14 (two free rounds: diagnosis, mechanism, fix) | 0 | $0.00000 | — |
| Phase 15 gate replays (28 attempts, 914 episodes) | see manifest | $97.33130 | not separately reconciled |
| Phase 16 (read-only audit, build, two reviews; no provider or W&B call) | 0 | $0.00000 | — |
| Phase 17 full loop (9 attempts, stopped CERTIFIED at attempt 9) | see manifest | $24.29386 | ≈$2.28 token-priced (unverified) |
| Phase 18 held-out check (1 attempt, 36 episodes, verdict HARM) | 202 (Actor) | $4.22180 | ≈$0.36 token-priced (unverified) |
| Phase 19 (clock-drift diagnosis and fix; local probes only, no provider or W&B call) | 0 | $0.00000 | — |
| Phase 20 development probe (69 pairs, 138 episodes, complete) | ≤1,104 Actor calls bound | $18.76820 | not separately reconciled |
| Phase 21 Actor replay probe (1,063 requests, V5_NOT_ADOPTED) | 1,063 (Actor) | $22.21670 | not separately reconciled |
| Phase 22 (build, two reviews, freeze, heldout-2 seal; no provider call) | 0 | $0.00000 | — |
| Phase 23 fixed-N loop (30 attempts, 3 certified) | see manifest | $77.29792 | not separately reconciled |
| Phase 24 heldout-2 check of 711bddb6 (1 attempt, 156 episodes, HARM) | see manifest | $17.11710 | not separately reconciled |
| Phase 25 Mechanic slot-2 replay probe (260 V4 requests; no arm recommended) | 260 (Mechanic) | $12.95840 | not separately reconciled |
| Phase 26 second completion gap probe (126 episodes; MR completes 36 of 36 vs B0 1 of 36) | see manifest | $17.05440 | not separately reconciled |
| Phase 27 Actor report-word replay probe (1,064 requests; NOT_RECOMMENDED) | 1,064 (Actor) | $22.23760 | not separately reconciled |
| Phase 30 narrow report-status field replay probe (860 requests; RECOMMENDED_FOR_A_LATER_LOOP; Phase 29 cancelled, $0) | 860 (Actor) | $17.97400 | not separately reconciled |
| Shared total | 2,232 + Phases 9-27 | **$652.90** | **$4.60950+** |

**Remaining conservative allowance: $329.12** (after Phase 30's $17.98, rounded up from $17.974; Phase 29 cancelled at $0; Phase 27 $22.24; Phase 26 $17.05; Phase 25 $12.96; Phase 24 $17.12; Phase 23 $77.30; Phase 22 $0; Phase 21 $22.22; Phase 20 $18.77; Phase 19 $0; Phase 18 $4.22; Phase 17 $24.29). (Phase 16's audit found the ledger rows actually sum to $436.45; the $0.28 is the Phase 6 probe counted twice. The higher figure is carried.) The rows above sum to $339.40; the headline through Phase 12 read $243.00 while its rows summed to $243.28, a pre-existing $0.28 discrepancy the size of one probe. The higher, more conservative figure is carried forward. Actual billed dollars are unavailable, not zero. Phases 3 and 4 have no unknown token usage, but billed cost is unknown for all of those requests. Phase 1's campaigns on the same day (`ccb81465`, `0ff8bbf4`, `2fdef056`, `9e7f10cd`; 1,294 calls, $27.59 conservative in `artifacts/lab.sqlite3`) belong to Phase 1's older separate allowance and are not part of this ceiling; Phase 2 additionally ran two campaigns in their own stores under `artifacts/phase2-2026-09-20/`. Allocations are not amounts actually spent. Phase 1's older separate allowance is documented in its own report.

## Phase 3 evidence inventory

| Experiment | Campaign / study | Result |
|---|---|---|
| A search | `campaign-7567578d3ed44d9880b3578672ce3725` | Eight distinct schedules; six discovery faults triggered. One C6 citation error reproduced 0/3. 11 episodes total; NO_CHANGE. |
| B recovery | `campaign-3f20fcd4d4b14566a6203d9c110e744c`; `completion-study-be77b3ad95e74968b8394e136e825a3d` | 18 episodes; healthy 3/3 complete, all 15 source/candidate notification trials safely unfinished. Two rejected candidates; NO_CHANGE. |
| B2 alternative Mechanic | `campaign-892eee83577a409b82e02deaf73a1a9e`; `completion-study-52a2c10f8944457bb2a8627452fdc584` | Five control episodes. Third source skipped notification entirely, fault untriggered; INCOMPLETE before any Mechanic request. |

All 34 episodes now have verified Weave evidence. B2's saved decision evidence map retains four verified episodes; later readback verified the fifth without updating/resuming that experiment. Preserve that distinction. Phase 3 totals: 13 completed tasks, 20 safe unresolved, one violation; 26/29 scheduled faults triggered. Mixed totals are not an accuracy benchmark.

Most useful original episodes:

- Phase 2 C3 `episode-5fe246fcd210419cb78913a7053a33ec`: two pre-acceptance transient notification failures, four UNKNOWN status reads, zero notification effects. Incorrect original PENDING report failed C5/C6; other source repetitions were truthful unresolved. Handwritten reference recovery is only a feasibility control.
- A `episode-f2e70efc465242bcbd6342e43f49e7e0`: real C6 citation typo despite successful business effects. Reproductions `episode-35d5e62a1a3844ddbf3d95ae32c401fc`, `episode-ef4b7897744b413e8bb8073d4e62a9cb`, `episode-f01a84a1cb954af8b3aa93b3a61a5118` all completed without violation.
- B `episode-31398c4cccf64d96ba1e8ba9604357ec`: rejected candidate, original truthful UNKNOWN / SAFE_UNRESOLVED, C1–C8 pass. Weave root `8d7381b0-e2de-4838-869e-f593b8bb9ea9`.
- B2 `episode-1bf7a46732994f72aafb992566bca1bc`: get_order, successful update_order, five notification status reads, no send_confirmation, original truthful unresolved report. Primary next-phase example.

B candidate versions: `policy-cb85b657ae564d3fb1a0790dbb6f22a9`, `policy-ded30ca74dea421b8f3699228463dd0f`. Both rejected; baseline `policy-v0` remains active everywhere.

## Phase 4 evidence inventory

| Study | Campaign / study | Result |
|---|---|---|
| Context v2 | `campaign-cd872e2df96c4d45bc56f2be5307ec85`; `context-study-0aeffe8cdf1d4a0cbcca48f90dbc8a67` | 60 episodes, 60/60 Weave verified, 321 calls; **REGRESSION** (3/3 C5 violations on `terminal-upgrade-rejection`; 1/3 completion gain on `notification-3`; `notification-2` incomplete after an untriggered control trial). |
| Context v3 | `campaign-65e356ebc1e04e3c8165d329152c56d5`; `context-study-0fb80165ac9547e8b3836476081a3288` | 60 episodes, 60/60 Weave verified, 332 calls; **REGRESSION** (2/3 C5 violations on the same case; same 1/3 completion gain; `notification-18` incomplete after an untriggered changed-arm trial). |

Configuration hashes: study 1 `a49ae960715a593ffc55dbb8b28826841c1b1daaa7a0f4e8bb3b0476f948de5b`. Study 1's configuration no longer verifies against the installed runtime, because declaring the v3 protocol changed every descriptor hash including the unchanged v1 control's; descriptors now declare only the keys that apply, so later additions cannot do this again. The control's behaviour was identical in both studies and that is independently established by rebuilding all 653 Actor requests from saved records.

**Both Phase 4 studies were adversarially reviewed after the fact** (six reviewers, every finding sent to a separate agent instructed to refute it; 18 survived, 15 did not). Three real code defects and four wrong numbers were found and fixed; the corrections are listed in `PHASE4_RESULTS.md`. Re-deciding both saved studies under the corrected rule reproduces REGRESSION with identical counts, so no published conclusion changed. Every regression bundle saved before this phase no longer validates against the regenerated contracts - see the pitfalls file. Saved artifacts are under `artifacts/phase4-2026-09-20/` and `artifacts/phase4-followup-2026-09-20/`: `before.sqlite3`, `frozen-source-*.json` (175 files, 0 changed during either run), `configuration.json`, `context-study-final.json`, `context-study-summary.json`, `budget-final.json`, `recording-final.json`, `campaign-final.json` and the backend logs.

Most useful Phase 4 episodes:

- `episode-a90cfe39567642f2be1795993359f6e3` (study 1, B0, `notification-2`): control never called `send_confirmation`, read its status five times, fault untriggered. The Phase 3 B2 pattern reproduced live.
- `episode-61b6abbd7f954505a162637f0dcab76c` (study 1, B0, `notification-3`): control reported `PENDING` with no PENDING ever observed; C5 and C6 failed. The Phase 2 C3 error reproduced live.
- `episode-7efc8116f463417090d2835c86a446ff` (study 1, P1, `notification-3`): the intended mechanism — after an `UNKNOWN` read the changed arm resent the confirmation and completed.
- `episode-d76e4198905a4109805abf68a29fdb1d` vs `episode-f32b862dba3d4f19925e2007ad244348` (study 1, `terminal-upgrade-rejection`): identical actions, `NOT_STARTED` versus `NOT_REQUIRED`, violation versus clean rejection.

## Files and fingerprints

Main store `artifacts/lab.sqlite3`; independent per-world databases `artifacts/worlds/`. Read them read-only for audits; use SQLite backup API for a consistent copy of a running WAL database. Never hand-edit records or pointers.

`artifacts/phase3-2026-09-20/` contains:

- `before.sqlite3`, `pre-restart.sqlite3`, `after.sqlite3`: consistent preservation snapshots.
- `baseline.json`, `git-status-before.txt`: starting inventory.
- `frozen-source-1.json`, `frozen-runtime-1.zip`, `frozen-b2.json`: exact source/configuration identities and original protocol hashes.
- `search-final-*`, `completion-final*`, `completion-b2-final*`: original saved results.
- `campaign-…-final-recording.json` and related files: final read-only exports including later synchronization.
- `completion-b-manual-evidence.json`: per-episode original-report/effect/journal verification.
- `final-accounting.json`, `restart-verification.json`: counts, costs and preservation checks.
- `backend-checks-final.log`, server logs and evidence-only retry records.

Runtime hash `155a436c5651707568348ed0a91d5afb5a12b2df1dc9c6b1e20e5fc452f22adb`; algorithm `67be60292bd726bdaf64c09acaf34c1eadca554c95cf9011c3d79386093ba47d`; manifest `7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483`.
A/B configuration `713b0c7f128cb5204f4cd7e66ff59a3e45c14b60fc59f5f6f0b02aeda5ed0341`.
B2 configuration `2a7fe11fe2631bbbd9e1fdfb3c634863085c4eb2c131daa6217f2799e801621a`.
All 173 frozen source files matched at close. All 29,485 pre-phase records, 12,369 events and 34 old pointers were unchanged. Final restart preserved all 30,812 then-current records plus events/pointers/call ledgers exactly. Readiness and browsing made no paid calls.

## Phase 5 evidence inventory

| Study | Campaign / study | Result |
|---|---|---|
| 5A V4 Mechanic | `campaign-578537fb59d54f468e16dcdf64d1df87`; `completion-study-889f75d6d170418e9ff654f409a1952b` | 12 episodes, 12/12 verified, 81 calls; **NO_CHANGE**. Two proposals, neither containing a notification retry; the second byte-identical to the first (`08084f7135c3`) while claiming to be materially different. |
| 5B V3.1 Mechanic | `campaign-d89e955f66854979bff23bd03d32aa21`; `completion-study-122d93e0dfa94c7484a46dd65b83aab2` | 12 episodes, 12/12 verified, 85 calls; **NO_CHANGE**. Same shape; second proposal byte-identical (`337e60e2f335`) and its explanation describes retrying the original send_confirmation while the policy contains no retry step. |

Predeclared read-out: **0 of 4 proposals contain `retry_original_request` for notifications.** Both studies passed their declared controls (3/3 valid source with zero completions, 3/3 valid healthy completing) and neither retained an invalid trial. Artifacts under `artifacts/phase5-2026-09-20/`.

## Phase 15 evidence inventory

`artifacts/phase15-2026-09-22/`: `replay-manifest.json`, `runner.log`, `backend.log`,
`simulator.log`. Replay-only; nothing promoted. 28 attempts, 914 episodes, **$97.33**.
Manifest and store reconcile with **0 discrepancies**.

| Read-out | Value |
|---|---|
| declared | 20 scored, attempt cap 34, spend guard $140, circuit breaker 6, `v4-indexed-evidence` |
| **primary** | **9 of 20 scored accepted**, Wilson [0.258, 0.658]; vs Phase 10 0 of 13, Fisher **p = 0.005**. Threshold was >=7; met. First time the declared n was reached |
| vs Phase 13 | 9/20 vs 5/13, p = 1.00 — a clean replication |
| **(b) untriggered rate, mandatory** | **2.02%** [1.27%, 3.22%] (P10 1.28%, P13 2.75%). Predicts 0.479 pass rate vs 0.450 observed |
| **(c) conditional — isolates the gate** | **zero-invalid batches: 9 of 10 accepted. With an invalid trial: 0 of 10.** Total separation |
| decomposition of 28 attempts | 9 accepted, 1 `NO_CHANGE`, 10 `INCOMPLETE`, 8 evidence deaths, **0 control-path deaths** |
| **S1 quality rejection** | Phase 15 **1 of 20** (`Expected outcome regressed within a validation case`) vs P10 8 of 13, p = 0.000529; pooled 11+13+15 **1 of 40**, p = 0.0000118. **No longer zero** |
| **S2 Phase 14 fix** | **0 of 28** create aborts vs 11 of 30, **p = 0.000334**; 0 of 914 episodes vs 11 of 849, **p = 0.000312**. No `ReadError` at all |
| **S3 yield** | **0.714** (20/28), inside the declared 0.68–0.74; P13 0.433 |
| contamination | 7 of 20 scored batches (35%) contained an `actor_transport_retry` event — above the ~20% estimated |
| integrity | `scorer_hash` and `actor_prompt_hash` unchanged; `algorithm_hash`/`runtime_hash`/`configuration_hash` CHANGED (declared before the run). `assess_pairs` source hash `783e8e58f91992f36066a2c6a152c4fbd242bd7e` recorded |

**The only remaining loss channel is evidence** — 8 of 28 attempts (29%), 7 `WaitingEvidence`
+ 1 `EvidenceDenied`. Nothing in Phases 13-15 addressed it.

## Phase 14 evidence inventory

**Cost $0.** No paid run, no provider or W&B calls. 16 agents, four investigation angles,
three adversarial lenses each. No new artifacts directory; the evidence is the store itself
plus `docs/part2/PHASE14_RESULTS.md`.

| Question | Answer |
|---|---|
| **which control call fails** | **`create()` — `POST /control/worlds`** |
| structural proof | `execute_slots` wraps `runner.run` in no try; `runner.run` has no finally and two blanket `except Exception`; `create()` is the only HTTP call in the unprotected window |
| forensic proof | all **14** `ReadError` studies store-wide leave exactly one slot `INTERRUPTED` with no `episodes` row; all **56** evidence-channel studies leave zero |
| sharper exclusion | `completion_study` sets `slot['status']` *before* the evidence-gateway await, so a gateway error would leave **zero** slots RUNNING |
| did the request reach the server | **no** — 0 of 3,730 world files carry the 14 episode_ids; 0 orphans with a Phase 13 mtime; an instrumented server counted 884 for 884 client successes |
| **why it fails** | **FOUND (2nd free round).** uvicorn arms its keep-alive timer when it finishes *writing* a response (`h11_impl.py:331`), so its deadline precedes the client's; the handler closes the transport without draining (`:372`); on macOS that emits **RST**, discarding the request before the app runs |
| no upper edge | hazard decays: [5.0,5.5) 11/155, [5.5,6.0) 2/67, [6.0,7.0) 0/76, [7.0,∞) 0/109. Zero above 6s has **P = 0.68**. The p=0.0009 "edge" becomes p=0.02–0.21 stratified; the **lower** edge survives at p < 5e-6 |
| best predictor | straddle `A < 5.0 <= gap`: 10/110 vs 1/761, Fisher **p = 7.0e-09**, beats the band by 2.9 logL |
| refuted | TIME_WAIT/port collision (72/72 served), teardown racing accept (216/216), fresh-connection reset (888 trials, 0). The victim is always a **reused** connection |
| **real fix** | `httpx.Limits(keepalive_expiry=2.0)` client-side so the client always closes first (verified: 4.9s idle old=REUSED, new=fresh) + `--timeout-keep-alive 75` server-side |
| backstop | bounded jittered `create()` retry, 3 attempts, transport-only. **551 of 551** induced failures recovered on attempt 2 |
| defects fixed in the retry | no jitter (12 of 14 lost unjittered vs 1 of 14 jittered) and an unclamped `CREATE_BACKOFF` index (`IndexError` at `CREATE_ATTEMPTS=4`) |
| verification | **592 backend tests**, integration 45; `scorer_hash` unchanged |

**Measured idempotency, per operation** (in-process against the real simulator):

| operation | on a repeat | retry-safe |
|---|---|---|
| `create` | same episode_id → two distinct world_ids, two files | **yes** (orphan is inert and unnameable) |
| `advance` non-observer | tick 2 → **4** | **no** — can flip `fault_triggered` → `valid_trial` → whether a pair qualifies |
| `advance` observer | **409 `INVALID_OBSERVER_ADVANCE`**, tick unchanged | yes (latched by `horizon_done`) |
| `snapshot` / `faults` | byte-identical | yes |

**Still open:** the teardown → `EvidenceDenied` route. 3 `SIMULATOR_OR_SCORER_ERROR`
episodes store-wide, each of which killed a study. Deliberately not bundled into this fix.

## Phase 13 evidence inventory

Saved under `artifacts/phase13-2026-09-21/` (`replay-manifest.json`, `runner.log`,
`settings-phase13.json`) and `artifacts/phase13-probe/`. Replay-only: no Mechanic call, no
proposal, nothing promoted. Policy under replay `policy-d2b12ec1325742f5ac1428ec28f19639`.

| Read-out | Value |
|---|---|
| declared | 20 scored replays, attempt cap 30, spend guard $170, `v4-indexed-evidence` |
| **primary** | **5 of 13 scored returned `OBSERVED_IMPROVEMENT`**, Wilson [0.177, 0.645]; vs Phase 10 0 of 13, Fisher **p = 0.039** |
| shortfall | declared 20 scored, reached **13** at the attempt cap — reported, not re-declared |
| scored decomposition | 8 `INCOMPLETE`, **0 `NO_CHANGE`**; pooled with Phase 11, 0 quality rejections in 20 scored |
| **secondary (null)** | yield 13/30 = **0.433** vs all-prior 20/39 = 0.513 and predicted ~0.6; Fisher **p = 0.63**. Phase 12's objective unmet |
| unscored causes | `ReadError` **11** (37% of attempts), `WaitingEvidence` 5, `EvidenceDenied` 1 |
| ingestion health | 5 `RETRYABLE_ERROR` of 848 episodes (**0.6%**, all `TRANSPORT`) — healthy; maps 1:1 onto the 5 `WaitingEvidence` deaths |
| actor transport retry | fired **4 times, 4 of 4 episodes survived**; Phase 10 had 10 failures and **0 of 10** survived; Fisher **p = 0.0037** (historical, not concurrent, control) |
| spend | $91.41660 run + $4.70250 probe = **$96.11910** |

**Two queries to get right next time.** Events are in their own `events` table, not in
`records` with `kind='events'` — searching `records` returns 0 and looks like "the feature
never fired". And `error_type` on a `completion_studies` record is written by
`completion_study._execute`'s own handler around `execute_slots`, so it names a failure
*inside* episode execution, not in the runner's polling.

## Phase 12 evidence inventory

`artifacts/phase12-2026-09-21/`: `before.sqlite3`, `frozen-source-phase12.json`,
`settings-phase12.json`, `backend-phase12.log`, `runner.log`, `replay-manifest.json`.

**Aborted on an external dependency; measured nothing.** 28 attempts, 0 scored, $8.15.
W&B Weave ingestion degraded from **0.9% to 31%** per-episode failure (19 `DEADLINE`,
9 `TRANSPORT`) between Phase 11 and Phase 12, so no 42-episode batch could verify.
**Not a code regression**: 0 `LAB_ERROR` in 91 episodes, 0 new provider failures, the new
retry never fired. The bounded blind retry (`CONNECTION_ERROR`, `REQUEST_TIMEOUT` only;
`EMPTY_FINAL_RESPONSE` excluded) is built, tested and **unmeasured**.

New guards: a runner circuit breaker (abort after 4 consecutive unscored attempts) and
`scripts/experiments/check_ingestion_health.py` — whose first version wrongly reported
HEALTHY because its query lacked `ORDER BY`; recorded rather than silently fixed.

## Phase 11 evidence inventory

Artifacts in `artifacts/phase11-2026-09-21/`: `before.sqlite3`, `frozen-source-phase11.json`,
`settings-phase11.json`, `backend-phase11.log`, `stage-a.log`, `stage-b.log`,
`replay-manifest.json` (Stage A) and `stage-b/replay-manifest.json` (Stage B) — every
attempt retained.

| | result |
|---|---|
| change | `faultlab-actor-context/v4-indexed-evidence`: observations shown as `obs-1 … obs-n`; decode is total, exact-match, unmatched tokens pass through verbatim |
| **declared primary** | **2 of 6 scored replays accepted, Fisher p = 0.088 — NOT significant** |
| pre-declared pooled | 3 of 7, p = 0.031 (pooling rule fixed before Stage B ran) |
| **quality rejections** | **8 of 13 (v1) → 0 of 7 (v4), p = 0.015** |
| citation corruption | 3.43% → **0 of 368 episodes**; ≥12-citation regime 30% → **0 of 14** |
| C1–C8 violation rate | **6% → 0%** |
| Phase 4 regression guard | **passes** — no target outcome lost, no violation gained; `notification-18` 66% → 92% |
| side effects checked | fault trigger 97.5% → 97.4%; actor calls 5.42 → 5.14; COMPLETED identical at 59% |
| unexpected | citation breadth **fell** 0.887 → 0.735 (judges predicted the opposite) |
| hashes | `scorer_hash` unchanged; v1/v2/v3 descriptor hashes byte-identical; only `source_hash` + derived moved |
| cost | $39.77270 (Stage A $4.45170, Stage B $35.32100) |

## Phase 10 evidence inventory

Artifacts in `artifacts/phase10-2026-09-21/`: `before.sqlite3` (53,131 records),
`frozen-source-phase10.json`, `settings-phase10.json`, `backend-phase10.log`, `runner.log`,
`replay-manifest.json` (all 26 attempts retained), `configuration-phase10.json`, and the two
citation analyses `pre-run-citation-analysis.txt` / `post-run-citation-analysis.txt`.

| | result |
|---|---|
| design | replay T15's policy through the frozen 42-episode validation batch, via the **unchanged** `execute_slots` and `assess_pairs` |
| primary read-out | **0 of 13 scored replays returned `OBSERVED_IMPROVEMENT`**; Wilson 95% [0.000, 0.228] |
| attempts | 26 (declared cap), 13 scored, 13 unscored and replaced; 828 live episodes |
| scored decomposition | 8 `NO_CHANGE`, 5 `INCOMPLETE` |
| violation rates | L **26/414 (6.3%)**, B0 **21/414 (5.1%)** — the policy adds ~1.2 points |
| cause | **62% of violating episodes (29/47) cite a fabricated evidence ID** |
| corruption rate | **3.43%** of 1,284 reports (pre-registered prior predicted 3.22% on 466) |
| signature | token `extremely` spliced into a hex ID **4 times** across Phases 8-10; others lose characters |
| worst case | `notification-18` (cites 13-14 of 15 observations): 12/50 L, 7/50 B0 |
| harness limitation | one `LAB_ERROR` aborts the whole 42-episode batch via the evidence gateway; 13 of 26 attempts died that way |
| cost | $93.82010 |

T15's policy is still `REJECTED`; no policy is ACCEPTED anywhere. Store after Phase 10:
83,180 records, 2,300 episodes.

## Phase 9 evidence inventory

Artifacts in `artifacts/phase9-2026-09-20/`: `before.sqlite3` (37,499 records / 1,090
episodes), `frozen-source-phase9.json` (now also freezing the two read-out scripts),
`settings-phase9-mechanic-v4.json`, `backend-phase9.log`, `runner.log`,
`replication-manifest.json` (every attempt, retained), `readout.txt`,
`configuration-phase9.json`, and the phase's most important artifact —
`qualifying-study-T15.json` and `qualifying-policy-T15.json`.

| | result |
|---|---|
| design | paired, interleaved, concurrent control; 16 attempts per arm on one backend; leading arm swapped each round |
| primary read-out | **T 3 of 14, C 1 of 11; Fisher exact two-sided p = 0.604 — not significant** |
| Phase 8 claim | **withdrawn** |
| first ever `SOURCE_QUALIFIED` | study T15 `completion-study-5b5ddb0843874dd5981d2a9abac54a77`, campaign in the manifest; L 3/3, B0 0/3, 0 violations |
| why it was rejected | one C6 violation in validation `notification-18`; the **Actor hallucinated** `evidence-a20c6f2a5a8547f1b445a025extremely-9372` (12 of 13 citations real). Baseline failed the same case independently on C5/C6 |
| L vs B0 violation rate | **16–28%** against **~3%** |
| duplicate second proposals | 16 of 32 studies |
| source-gap leakage | **3.4%** across 88 valid triggered baseline control episodes (refines Phase 6's 4.4% from 45) |
| cost | $53.56838 |

Store after Phase 9: 53,131 records, 1,472 episodes. No policy is ACCEPTED anywhere;
`policy-v0` remains the incumbent in every campaign.

## Phase 8 evidence inventory

Artifacts in `artifacts/phase8-2026-09-20/`: `before.sqlite3` (36,420 records / 1,064 episodes),
`frozen-source-phase8.json`, `settings-8a-mechanic-v4.json`, `settings-8b-mechanic-v31.json`,
`backend-8a.log`, `backend-8b.log`, `campaign-8a.txt`, `campaign-8b.txt`,
`study-8a-final.json`, `study-8b-final.json`, `configuration-8a.json`, `configuration-8b.json`,
`proposal-context-8a-{1,2}.json`, `proposal-context-8b-{1,2}.json`, `budget-8a.json`,
`budget-8b.json`, `final-checks.log`.

| Study | Identifiers | Result |
|---|---|---|
| 8A V4, per-episode `task_outcome` | `campaign-cdb43a228401458b91b77a85c87815e8`; `completion-study-ba0a7595769542e899b0bcf3d9e42ff6` | 12 episodes, 12/12 verified, 74 calls; **NO_CHANGE**. **2 of 2 proposals contain `retry_original_request` for notifications** — first in the project. Candidate `d4bc993e1854` completed the source case live in 2 of 3 (`policy_steps=4`, replay SUCCEEDED at tick 8); rejected at 2 of 3 with a C6 violation in the third. An independent baseline episode failed C5+C6. Second proposal byte-identical to the first. |
| 8B V3.1, per-episode `task_outcome` | `campaign-20bd66acb8244a92b6747ee4032f7183`; `completion-study-fe0e1bde846144d6bc93b6a094898e26` | 14 episodes, 13/13 verified, 101 calls; **INCOMPLETE** — candidate-2's first L trial died with a provider `CONNECTION_ERROR`, retained as `LAB_ERROR` without retry, 4 slots unattempted. **0 of 2.** First proposal `337e60e2f335` is byte-identical to V3.1's Phase 5 output. |

Both saved proposal contexts carry `format: faultlab-compact-evidence/v2-task-outcome` with
`task_outcome` on every episode row. Only `algorithm_hash` and the derived `runtime_hash`
moved against the stored Phase 6 configuration; exactly two source files changed.
Store after Phase 8: 37,499 records, 1,090 episodes.

## Phase 7 evidence inventory

Artifacts in `artifacts/phase7-2026-09-20/`: `locate-DeepSeek-V4-Pro-0813.json`,
`locate-DeepSeek-V3.1.json`. Non-scoring: no campaign, study, trial or policy was created,
and nothing was fed back. Part B was **not run**; no paid call was made in it.

## Phase 6 evidence inventory

| Item | Identity | Result |
|---|---|---|
| Part A probe | `artifacts/phase6-2026-09-20/probe-*.json` | 8 non-scoring requests, 2 models x with/without brief x 2 repeats. **None said a replay is forbidden**; 6 of 8 said PERMITTED and quoted the contract. Fed into nothing. |
| 6A V4, clarified brief | `campaign-8f57ac087b48435aa40739f3633dc838`; `completion-study-7aea25bfc3e34ac797b42e7d5128b110` | 12 episodes, 12/12 verified, 77 calls; **NO_CHANGE**, 0 of 2 proposals contained a notification retry, second byte-identical (`1673dabdb4f4`). One retained invalid trial in candidate-1 that would have aborted the run before Phase 6. |
| 6B V3.1, clarified brief | `campaign-528752ed7c4642e9b7ef967ccab53f1f`; `completion-study-387f536ab6a84e64b444719ff8fd557a` | 6 episodes, 6/6 verified, 36 calls; **NO_CHANGE at controls** — one of three baseline trials completed, so the gap did not reproduce and no proposal was requested. |

The brief clarification is a permanent declared source change; it moved only `source_hash`. Before/after copies are archived as `completion-brief-before.md` and `completion-brief-after.md`.

**Measured source-gap leakage:** the baseline policy completes the source case in **2 of 45** valid triggered live episodes (4.4%), so a three-trial zero-completion gate fails ~13% of the time by chance. Address prospectively with more declared trials, never by loosening a threshold.

## API routes and commands

Read-only: `GET /api/config/status`, `/api/readiness`, `/api/campaigns/ID`, `/api/campaigns/ID/configuration`, `/api/campaigns/ID/budget`, `/api/campaigns/ID/search-attempts`, `/api/campaigns/ID/completion-studies`, `/api/completion-studies/STUDY_ID`, `/api/campaigns/ID/context-studies`, `/api/context-studies/STUDY_ID`, `/api/campaigns/ID/recording`, `/api/campaigns/ID/experiments`.

`./scripts/run-context-study.sh --status STUDY_ID` only reads, and `scripts/experiments/summarize_context_study.py STUDY_ID` prints the comparison tables from the read-only API. `--execute-live` creates fresh paid work.

`./scripts/run-completion-study.sh --status STUDY_ID` only reads. `--execute-live --wait` creates fresh paid work and must not be used merely to inspect status. POST `/api/campaigns/ID/retry-evidence` with explicit episode IDs synchronizes existing evidence only; it does not rerun models or make a failed study successful. Check its returned `/api/evidence-retries/REQUEST_ID` until terminal before claiming verification.

Aria publication is disabled. Generic sponsor status may show PENDING even when specific episode evidence is verified; inspect the actual evidence records. Historical runtime 2 registrations can fail compatibility against current source; do not weaken validation to reuse one. Read the current regression guide before fresh replay.


## Phase 16 evidence inventory (2026-09-22, $0)

- `artifacts/phase16-2026-09-22/gate-freeze-before.json` and `gate-freeze-after.json`
  (sha256 `96dc32a0…`): gate fingerprints before and after.
- `artifacts/phase16-2026-09-22/source-before/`: verbatim pre-edit copies, with `SHA256SUMS`.
- `artifacts/phase16-2026-09-22/settings-phase17.json`: a byte copy of the Phase 9 settings,
  sha256 `1e2002d3…`.
- Expected `configuration_hash` `c4169ee4…`, from `scripts/experiments/expected_configuration.py`.
- Backups:
  - git branch `backup/part2-2026-09-22`, a snapshot of all Part 2 work taken without
    touching `main` or the working tree;
  - `~/FaultLab_Backups/2026-09-22-pre-phase16/`: git bundle, full `artifacts/` copy, the
    store copied via the SQLite backup API, the specs, and a README with restore steps;
  - both are on the same disk as the originals. Copy them to external storage for real
    protection.


## Phase 17 evidence inventory (2026-09-23, $24.29 bound)

- `artifacts/phase17-2026-09-23/full-loop-manifest.json`: every attempt and all spend.
  Reconciled against the store: 0 discrepancies, 0 untracked.
- `runner.log`, `backend.log`, `simulator.log`, and `launch_backend.py` (the exact backend
  launch recipe: the frozen settings, non-empty values, no reload).
- **Certified study:** `completion-study-2c2a11971fce4884a382c875bebb87f1`.
- **Certified policy:** hash `dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521`,
  saved as `PROPOSED`.

## Phase 18-19 evidence and live state (2026-09-23)

- **Phase 18 held-out check:** `artifacts/phase18-2026-09-23/`
  - check `heldout-check-9c5389c06d4b498aadb330643972c9ae`;
  - campaign `campaign-86d7c4325a4b474cbba797002ff84300`;
  - configuration `1b6e5ed0…`;
  - verdict HARM.
- **Phase 19:** `artifacts/phase19-2026-09-23/`
  - freezes: before `3619a4aa…`, after `3636ca21…`;
  - `source-before/`;
  - `diagnosis/` (probe scripts and saved outputs);
  - `clock-drift-*.txt`, `loop-latency-*.txt`, `expected-configuration.txt`.
- **Backend:** restarted on the Phase 19 code at 10:33:42 local on 2026-09-23 (pid 58539),
  via `artifacts/phase17-2026-09-23/launch_backend.py`. It logs to
  `artifacts/phase19-2026-09-23/backend.log`.
- **Simulator:** pid 33848, started by `scripts/start-simulator.sh` with
  `--timeout-keep-alive 75`. It logs to `artifacts/phase17-2026-09-23/simulator.log`.
- **Dashboard:** a Vite dev server (pid 6469, since 2026-09-13) serves the dashboard at
  `localhost:5173`. An open tab polls the backend once a second.
- **Expected `configuration_hash`** for the Phase 17 settings on the Phase 19 code:
  `0a33aa51cf125cadcfc1dfeaf640950f9e18e0dd89576ec24202a414893aee98`.

