# Setup

For shared orders/payment evidence, follow [the incident-evidence guide](incident-evidence.md).
It uses the existing backend installation and adds no dependency or provider requirement.

October 9 shared-evidence verification: first frozen candidate **3407 passed, 232 skipped, 2 warnings in 1272.07s (0:21:12)**;
final Unicode boundary repair **248 incident tests passed**, followed by 26 CLI checks
over 15 fresh worlds. Full-suite and final focused results cover different frozen candidates.
Frontend tests/build/browser checks passed; see [the exact verification scope](INCIDENT_EVIDENCE_2026-10-09.md).

For the portable rejection regression, start with [the offline example](offline-regression.md).
`./scripts/setup.sh --backend-only` installs its Python dependencies without Node or `.env` creation.
The full dashboard workflow below is unchanged.

To test a self-contained Python decision agent, follow [the local-agent guide](local-agent.md).
It uses the same backend installation and requires an explicitly selected trusted source file.

To exercise a user-owned smolagents constructor under native framework orchestration,
follow [the native-agent guide](native-agent.md). It uses the pinned backend dependencies
and a declared deterministic model double; it needs no provider credentials.

Native-agent verification on October 9, 2026: **3,177 backend tests passed**,
234 existing skips and 2 deprecation warnings, in 20 minutes 6 seconds. All 36 native-agent
tests passed. Eight separate-installation CLI/portable-test outcomes, independent checks
of eight saved worlds, and manual report review passed. Frontend tests (373), build,
19 browser fixture checks and one real-backend browser check passed; one opt-in fixture
was skipped. See [the verification record](NATIVE_AGENT_2026-10-09.md) for source
identity, corrected findings and limits. The earlier [local-agent record](LOCAL_AGENT_2026-10-08.md)
describes that milestone's separate evidence.

## Install and test (start here)

These steps were re-run in a fresh clone on 2026-09-29 (macOS on Apple silicon). CI runs the same
scripts on Ubuntu 24.04. Windows has not been tried. Offline work needs no accounts or keys and
makes no model calls.

**You need:**

- **Python 3.12.** `.python-version` says 3.12.8. `setup.sh` runs `python3.12`, or the interpreter
  named in `FAULTLAB_PYTHON`.
- **Node and npm.** Node 20.19 or a later 20.x, or Node 22.12 or later. This is `package.json`'s
  `engines` range (`^20.19.0 || >=22.12.0`). `.nvmrc` pins 20.19.0, which CI also uses.
- **A browser for the browser tests.** Google Chrome in its usual macOS place is used when present.
  Otherwise install Playwright's Chromium once: `cd frontend && npx playwright install chromium`.
  On Linux, add `--with-deps`.

**1. Install (about 1 minute; 32 seconds in the fresh clone).**

```sh
git clone <this repository> faultlab
cd faultlab
./scripts/setup.sh
```

`setup.sh` creates `.venv`, installs the locked Python packages (`backend/requirements.lock`) and runs
`npm ci` for the locked frontend packages. It downloads about 100 Python and 110 npm packages.

It also creates `.env` when there is none. That file is a copy of `.env.example` (safe defaults, no
keys), readable only by you (mode 0600). The W&B project named in it is the team's; set your own before
a live run. An existing `.env` is never overwritten. Offline work needs nothing in it.
Fill it in only for live runs (see the [quick start](user-guide.md)), and never commit it.

**2. Test (about 18 minutes; the backend stage alone takes 15 to 17).**

```sh
./scripts/test.sh                          # all four stages: backend, frontend, build, browser
./scripts/test.sh frontend build browser   # only the quick stages, about 40 seconds
```

- **Every stage runs**, even when an earlier one fails.
- **The script ends with a summary**: one PASSED or FAILED line per stage. It exits non-zero if any
  stage failed.
- **Ctrl+C stops the whole run at once** (exit 130). Later stages do not start, so no dashboard is
  started for the browser stage.
- **The browser stage starts its own dashboard** on port 5173 (or `FAULTLAB_DASHBOARD_PORT`). If
  something already listens there, the stage stops with Playwright's "already used" error. It does not
  test that other dashboard. Set `FAULTLAB_BROWSER_REUSE_DASHBOARD=1` only when you mean to test a
  dashboard you started yourself.

Results on 2026-09-29:

| where | backend | frontend unit | build | browser |
|---|---|---|---|---|
| fresh clone | 2,704 passed, 232 skipped, 0 failed (19 min) | 329 passed | passes | 17 passed, 1 skipped |
| the team's workspace | 2,756 passed, 180 skipped, 0 failed (18 min) | 329 passed | passes | 17 passed, 1 skipped |

- **The build prints one warning**, about a bundle larger than 500 kB. It is only advice.
- **The skipped browser test** is the opt-in real-backend test described below.
- **A fresh clone skips more tests** (232 instead of 180). Many experiment tests need the team's
  local lab stores, frozen code trees or settings files under `artifacts/`, which Git ignores. Those
  tests skip and name the file or store they need. `../.venv/bin/python -m pytest -rs`, run inside
  `backend/`, lists the reasons.
  No test should fail in a clone. A failure there is a real problem.
- **One browser test uses the real backend and is off by default.** To run it, start the simulator
  and backend without a dashboard, then run the browser tests with `FAULTLAB_BROWSER_LOCAL=1`:

  ```sh
  ./scripts/start-local.sh --no-frontend --data-dir "$HOME/FaultLab_Runs/browser-check"
  cd frontend && FAULTLAB_BROWSER_LOCAL=1 npm run test:browser     # in a second terminal
  ```

**3. Run it (offline, no model calls).**

```sh
./scripts/start-local.sh --data-dir "$HOME/FaultLab_Runs/my-workspace"
```

- **What starts:** the simulator, the backend and the dashboard, all using that one data folder.
  The folder is created if needed. Keep it outside the repository.
- **Try one run:** open http://127.0.0.1:5173, choose **Offline reference smoke**, then create and
  start a campaign.
- **Or from a second terminal:** `./scripts/run-demo.sh --mode baseline --wait` runs one offline
  reference attempt and prints the result.
- **To stop:** press Ctrl+C in the first terminal. That stops all three services.

[Local operation](local-operation.md) covers archives, recovery and running services one at a time.

**Ports.** Three settings choose the local ports. Unset means the usual port.

| setting | service | default |
|---|---|---|
| `FAULTLAB_SIMULATOR_PORT` | simulator (the fake shop) | 8001 |
| `FAULTLAB_BACKEND_PORT` | backend API | 8000 |
| `FAULTLAB_DASHBOARD_PORT` | dashboard | 5173 |

Export them in each terminal you use, before any FaultLab script. Every script reads them:

- `start-local.sh` and the three separate start scripts;
- the dashboard's `/api` proxy and the browser tests;
- the command-line tools behind `run-demo.sh`, `export-evidence.sh`, `run-audit.sh` and the
  `run-*-study.sh` scripts.

For example, a second checkout can run next to the first:

```sh
export FAULTLAB_SIMULATOR_PORT=18001 FAULTLAB_BACKEND_PORT=18000 FAULTLAB_DASHBOARD_PORT=15173
./scripts/start-local.sh --data-dir "$HOME/FaultLab_Runs/second-workspace"
```

A value that is not a whole number from 1 to 65535 is refused before anything starts.

The command-line tools print `Using the FaultLab backend at http://127.0.0.1:PORT.` before they create,
start or stop anything. If no backend answers, they name the address they tried and whether
`FAULTLAB_BACKEND_PORT` was set.

## Setup history (dated records)

For current results, remaining work and budget, read [CURRENT_STATUS.md](../CURRENT_STATUS.md).
The dated sections below describe their original runs and are kept as history.

- **Their commands and test counts are not current instructions.** Use the section above.
- **Local-only references:** paths under `artifacts/` and the campaign and settings references below
  belong to the team's own git-ignored evidence. A fresh clone does not include them.
- **Where the IDs are:** the experiment IDs are in the dated results reports under `docs/part2/`.

September 27 reviewed campaign onboarding: [workflow and verification](PRODUCT_ONBOARDING_REVIEW_2026-09-27.md).
Use the [quick start](user-guide.md) to choose a reviewed agent/task/case, save an idle immutable plan,
then explicitly Start. Registration and setup make no model calls. Current source `d1845765…` passed
**2,224 backend tests, 180 existing skips, zero failures**, two warnings, 791.81 seconds. Frontend:
**219 tests, build and ten browser fixtures passed**, one opt-in actual-backend skip. Actual six-case
UI execution, recording download, restart, audit freeze and archive verification passed. New provider
cost $0; temporary services stopped. Previous dated results below remain historical evidence.

September 27 product durability: use the [local operation guide](local-operation.md) for the paired
launcher, explicit data directory, read-only archive and recovery behavior. The [durability review](PRODUCT_DURABILITY_REVIEW_2026-09-27.md)
records ownership, atomic job finalization, independent dashboard reads and actual manual restart checks.
Frontend: **206 tests, production build and eight browser fixtures passed**. A fresh offline dashboard
run completed one upgrade/confirmation and all eight checks with zero model calls; a real restart
preserved every saved record/event/pointer. Final full backend: **2,123 passed, 180 existing skips, zero failures**, two warnings, 727.37 seconds.
Three test fixtures were corrected to close the first owner before simulating restart; all assertions
remain. New provider cost $0.

September 27 product reliability work: [core workflow audit and verification](PRODUCT_CORE_REVIEW_2026-09-27.md).
Campaign history, saved regression execution history and readiness are now in the dashboard. Saved-record reads run outside
the scheduler event loop. Retained candidate violations, lab/world clock disagreement, interrupted
batches and cleanup failures have explicit handling. Final verification: **2,010 backend tests passed,
180 existing skips; 192 frontend tests, build and six browser checks passed**. A separate real-dashboard
reference run and direct world reconstruction passed. New provider cost $0. No new live result is claimed.

September 27 Phase 31 follow-up: [report-finalization fix, offline reconstruction and saved-dashboard
rehearsal](part2/REPORT_FINALIZATION_FIX_2026-09-27.md). This is a new runtime, with no paid calls;
the historical reserved evaluation remains INCOMPLETE. Use the current status page for final check
counts and the [saved-evidence demo guide](part2/PHASE31_DEMO_GUIDE.md) for a read-only presentation.

Updated September 20, 2026 on macOS. Team: Gatekeeper. Product: FaultLab. React evidence UI, FastAPI coordinator and a separate private-world HTTP simulator run locally. Use the [quick start](user-guide.md) for runnable steps and [Phase 3 results](part2/PHASE3_RESULTS.md) for current measurements. Earlier records below are preserved history.

## Current Phase 3 setup and verification

Completed checks: **519 backend tests, 100 frontend tests, production build and three browser fixtures**. Actual UI checks opened live search and both completion studies, original proposals, reports and Weave links. The unchanged final backend restart preserved all 30,812 records, events, pointers and paid-call ledgers; readiness makes no provider calls.

The running backend uses `artifacts/phase3-2026-09-20/settings-b2.json`: Actor V3.1, Explorer and Mechanic V4 Pro-0813, Aria off, same confirmed W&B project and $400 allocation inside the shared $1,000 ceiling. The `.env` file was not changed. `settings.json` in the same directory preserves the A/B configuration with Mechanic V3.1. Both use the same frozen runtime `155a436c5651707568348ed0a91d5afb5a12b2df1dc9c6b1e20e5fc452f22adb`. B2's configuration is `2a7fe11fe2631bbbd9e1fdfb3c634863085c4eb2c131daa6217f2799e801621a`.

Phase 3 retained 34 live episodes and 223 model requests. Every trace is now verified. A and B ended NO_CHANGE; B2 stopped INCOMPLETE on an untriggered source fault before its Mechanic was called. No candidate was accepted or activated. Combined Phase 2/3 conservative charges are $23.81478; actual billed dollars remain unavailable. Detailed counts, the distinction between saved decision evidence and later trace synchronization, and remaining proof requirements are in the results report.

## Current Phase 2 setup and verification

Runtime 2 uses DeepSeek V3.1 for Actor and Mechanic, and DeepSeek V4 Pro-0813 for Explorer with thinking disabled. The destination was the team's confirmed W&B entity and project (the project name is case-sensitive); use your own `WANDB_ENTITY` and `WANDB_PROJECT`. Matching input/output prices per million tokens are $0.55/$1.65 for V3.1 and $1.31/$3.96 for V4. Aria publication remains disabled.

The saved non-secret settings are `artifacts/phase2-2026-09-20/settings.json`. They set a $400 per-campaign allocation, 6,000 model calls and 204 million combined tokens. Each call admits at most 32,000 input and 2,000 output tokens. Phase 2's separately authorized $1,000 cumulative ceiling covers all its campaigns, stores and probes together; it is tracked across those records, not enforced by a single global account limiter. Existing protected-study reservations remain enabled. Unknown prices or usage are never treated as zero.

The frozen runtime fingerprint is `1261f1f30b3212ec9440e6faf14055656ea44c6a47ed0856563167b0892891a8`; the main $400 configuration is `c58c7dc19ecb1eb63d1c00bacd84fc1dd0628f8cab6f44d73cffb4c52414f4ef`. Keep source, role settings, rates, caps and the local store consistent when reusing registrations. A CLI in another terminal must load the same overrides as the backend. The quick start includes a helper to load the saved settings without changing `.env`.

Runtime 2's `faultlab-reference-final-report/v1` protocol requests a strict report schema on the reference Actor's already report-required turns. It applies equally to baseline and candidate arms, with the same prompt, business tools, eight-turn/90-second limits and fixed checks. The model's original response is retained and scored; no answer is rewritten. Correct structure does not guarantee correct evidence citations. Native smolagents behavior is unchanged. This is a baseline engineering change, not a learned policy improvement.

Latest completed checks: **471 backend tests, 61 frontend tests, production build and three browser fixtures passed**. Manual dashboard inspection after restart loaded the imported B incident, opened its saved execution through **Saved execution ID → Open saved execution**, displayed three trials/24 calls, and opened the original C6-failing report. That read-only action made no new model calls. The opt-in automated actual-server smoke was skipped; the manual workflow passed. Independent UI and accounting review found no blocking issue. Live results:

- C2 ended `NO_CHANGE`: six completed tasks, two safe unresolved, zero violations, but only five of eight scheduled faults triggered. No repair was proposed or accepted.
- B's saved incident was exported to `artifacts/phase2-2026-09-20/incident-b-export`, validated against the runtime 2 reference registration, and played back without model calls. A fresh execution in a new campaign produced two safe unresolved results and one C6 citation violation. The original C5 missing-report failure reproduced zero of three times. All three Weave traces verified; this was baseline incident execution, not accepted-policy transfer.
- C3 completed 36 valid development trials, with all 30 faults triggered and no infrastructure errors. The 18 live-model trials had 12 completed, three correctly rejected, two safe unresolved and one violation. The 18 handwritten-reference trials had 15 completed, three correctly rejected and no violations. All 18 live traces and the evaluation verified.

Phase 2 totals: 149 episodes (131 live and 18 offline), 886 model calls including four schema probes, 131 verified live episode traces and no unknown usage. Conservative dispatched bound: $18.92256; known token-price estimate: $1.77596; actual billed dollars unavailable. No learned policy was accepted, so accepted-policy restart persistence, protected final evaluation and independent-agent transfer remain unclaimed. The backend restarted unchanged with saved campaigns, pointers and counts preserved; that does not demonstrate persistence of an accepted policy.

## Workspace

`faultlab/` was created beside `Brainstorm/`, `Hackthon_info/`, and `Idea_Planning_docs/`.
Those folders were left unchanged. There was no parent Git repository; only `faultlab/`
was initialized, with branch `main`.

The GitHub owner confirmed by the user is `ShreeBohara`. The remote is now the user-confirmed public
repository `https://github.com/ShreeBohara/faultlab`. GitHub authentication was
verified using the existing local login; no global Git configuration was changed.

## Foundation tool and dependency versions — September 12

| Component | Version |
| --- | --- |
| Node.js | 20.19.0 |
| npm | 10.8.2 |
| Python in `.venv` | 3.12.8 |
| Git | 2.52.0 |
| GitHub CLI | 2.88.1 |
| React / React DOM | 19.3.0 |
| TypeScript | 7.0.2 |
| Vite | 8.3.0 |
| Vite React plugin | 6.1.1 |
| FastAPI | 0.141.1 |
| Uvicorn | 0.52.4 |
| python-dotenv | 1.2.3 |
| OpenAI-compatible Python client | 3.13.0 |
| Weave | 0.53.9 |
| pytest | 9.1.1 |
| httpx | 0.28.1 |

`backend/requirements.lock` captures the complete installed Python environment;
`backend/requirements.txt` records exact direct dependencies. npm's resolved dependencies
are locked in `frontend/package-lock.json`.

The shell initially selected Python 3.8 inside the new directory. The empty setup
environment was recreated with the already installed Python 3.12.8. `scripts/setup.sh`
explicitly uses `python3.12` (or `FAULTLAB_PYTHON`) and checks the environment version.
No system tools were installed or upgraded.

## Historical foundation checks — September 12

These checks predate live implementation and the owner's decision to make the repository public. They are not the current provider or visibility status.

| Component | Result | Evidence / next action |
| --- | --- | --- |
| Python dependencies | Passed | `pip check`: no broken requirements. |
| Backend tests | Passed | All 20 tests passed with outbound DNS and socket connections blocked: seven health/configuration tests and 13 provider-check tests. |
| Provider SDK compatibility | Passed offline | Installed OpenAI client construction and Weave settings/op APIs checked without network access; mocked cases verify attribution, bounds, sanitized errors, and trace verification. |
| Frontend production build | Passed | `npm run build` passed TypeScript and Vite compilation. |
| Frontend dependencies | Passed | Install audit reported zero vulnerabilities. |
| Browser → Vite → backend | Passed | Browser at `http://127.0.0.1:5173` showed `Backend connected`, `status: ok`, `service: faultlab-backend`; recheck also succeeded. |
| Local development binding | Passed | Uvicorn on `127.0.0.1:8000`; Vite on `127.0.0.1:5173`. |
| Secret exclusions | Passed | `.env`, secret variants, virtualenv, node_modules, build output, and local database paths are ignored; `.env.example` remains trackable. |
| GitHub authentication | Passed | Existing ShreeBohara login verified; owner confirmed. |
| GitHub remote | Passed | `ShreeBohara/faultlab` created and independently verified private; `main` pushed and GitHub's commit SHA matched the local scaffold commit. |
| W&B access / models | Not tested | Await key entry in local `.env` and user's confirmation before discovery. |
| W&B generation / Weave upload | Not tested | Discover models, save one verified ID as `WANDB_MODEL`, then explicitly run one traced request. |
| TypeSafe | Blocked | Not configured — awaiting sponsor instructions. |

The foundation tests reported an upstream Starlette/AnyIO deprecation warning;
it does not prevent health checks or tests from passing.

## Historical provider setup — September 12, superseded

The initial setup recorded the team's W&B entity and a lower-case project name.
At that checkpoint access and credits had not been verified. Subsequent live work confirmed the team's
destination with a capitalised project name. Use your own entity and project, spelled exactly as in W&B.
Credentials remain in the local `.env`.

The original provider-check sequence was:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity YOUR_WANDB_ENTITY
```

Save an exact returned ID to local `WANDB_MODEL`. Only then run the explicit one-request
generation check:

```sh
./scripts/check-provider.sh wandb --generate --confirm-entity YOUR_WANDB_ENTITY
```

That initial generation check used 32 output tokens and a 20-second request timeout, with SDK
automatic retries disabled. The script uses the same explicit entity/project for
inference attribution and Weave, and verifies the saved trace before claiming success.
Normal startup, the browser, health checks, and offline tests never call either service.
No live connection result was claimed at that foundation checkpoint. Current live checks and traces are recorded above; the current quick start uses the 2,000-output-token limit.

For TypeSafe, obtain the sponsor's official quickstart or sample request, endpoint,
model ID, authentication instructions, and credentials. The reserved `TYPESAFE_*`
settings do not establish its protocol. No fallback provider is used.

## Official references consulted

- [Vite getting started and Node requirements](https://vite.dev/guide/)
- [W&B Inference endpoint, attribution, discovery, and Weave integration](https://docs.wandb.ai/weave/guides/integrations/inference)
- [Weave Python SDK source](https://github.com/wandb/weave)

Keep this file factual: update the result rows after actual checks, and keep real keys,
authorization headers, local secret files, and SDK debug dumps out of the repository.

## Implementation baseline (2026-09-12)

The explicit implementation request supersedes setup-only scope. Before adding product code,
`./scripts/test.sh` passed 20 backend tests and the TypeScript/Vite production build (139 ms
Vite phase). Existing FastAPI/React/provider checks remain prior scaffold work. No `.env`
contents were printed or overwritten and no provider calls were made. New schemas use
Pydantic 2.13.5; runtime integration pins are listed in requirements.txt/requirements.lock.

The initial frozen profiles were: `offline-v1`, labeled offline deterministic smoke; `live-v1`, requiring
`FAULTLAB_LIVE_ENABLED=true`, a matching `FAULTLAB_CONFIRMED_ENTITY`, configured W&B
model/project/credentials and explicit Start. Initial provider budget maxima were 6000 model calls,
60M combined tokens and $100 with verified pricing. Unknown cost was not zero. The
1064-call reserve protects audit, external and selector studies. Each episode admits at
most 18 HTTP attempts, 8 actor calls, 4 waits, 20 ticks, 32 policy steps and 90 seconds.
Capability scope is orders.upgrade_then_confirm/v1. Registry identities are reviewed locally;
no API or bundle can install arbitrary code. See integration-ledger.md for evidence gates.

Input admission for the initial gpt-oss model uses locally stored, digest-verified o200k
BPE ranks through tiktoken 0.14.0, with a framing reserve. Startup and tests never download
tokenizer assets. Unknown model families retain a conservative byte bound until reviewed.
The tokenizer metadata/license lives in contracts/tokenizer; actual provider usage remains
separate from conservative admission/reservation counts. Oversized essential evidence must
be reported as an input/harness limitation, not an invented agent mistake.


## Current implementation commands

Run `./scripts/setup.sh` to install the locked local dependencies. For live Phase 2 work, follow the explicit model/rate/cap overrides in the [quick start](user-guide.md), using `./scripts/start-simulator.sh`, `./scripts/start-live-backend.sh` and `./scripts/start-frontend.sh` in three terminals. Starting services makes no provider calls. Keep code and settings frozen during an experiment; the live launcher disables automatic reload. Both launchers now use the application model/context defaults described in CURRENT_STATUS.md, with explicit environment overrides respected. The live launcher does not assert historical prices; verified prices must be configured before live admission. The default campaign cap remains $100. `./scripts/start-backend.sh` is the development server, not the frozen live launcher. The UI is
http://127.0.0.1:5173. `./scripts/test.sh` runs backend tests, UI tests, build and browser
fixtures without providers. Browser tests use local Google Chrome when available; otherwise
install the local Playwright Chromium dependency with `cd frontend && npx playwright install chromium`.
With backend/simulator running, `cd frontend && FAULTLAB_BROWSER_LOCAL=1 npm run test:browser`
adds the actual local HTTP workflow. See README.md and docs/regression-runner.md for all
read-only export and explicitly enabled fresh-run commands.

Live campaign admission additionally requires verified nonnegative input/output pricing,
exact `FAULTLAB_PRICING_MODEL` match and `FAULTLAB_PRICING_VERIFIED=true`. Unknown pricing
blocks campaign admission; it is never interpreted as zero dollars. The separate one-request
provider compatibility check remains independently bounded. Historical GPT-OSS, Llama and DeepSeek compatibility observations remain in [model selection](model-selection.md); they do not replace the current frozen role settings above.


## Historical live verification — 2026-09-13

That verification used DeepSeek V4 Pro-0813 with W&B’s documented thinking disabled, JSON mode, temperature zero, 32K input/2K output admission and matching verified prices. The then-current quick-start connection check and healthy order passed with verified Weave readback. The full suite passed 356 backend tests, 20 frontend tests, production build and three browser checks; the opt-in offline browser execution was skipped and the actual live V4 dashboard was checked separately. Historical learning outcomes, including unreached repair stages, remain explicit in `docs/learning-results.md`.


## Historical Phase 1 verification — 2026-09-20

422 backend tests and 34 frontend tests passed, with the production build and three browser fixtures. The final registration-label change was followed by a fresh frontend test/build pass. Actual browser checks verified the local HTTP connection, one completed offline baseline (one fresh world, zero model calls), reload/read-only playback, incident inspection, and a three-world live regression with all three parent/tool traces read back from Weave.

Phase 1 used V3.1 as Actor, V4 Pro 0813 as Explorer, and separately tested V4 Pro and V3.1 as Mechanic. These were explicit launcher overrides; the general launcher still defaults to Llama 3.1 8B. The current walkthrough records the overrides and matching rates. No `.env` was overwritten, no system-wide tool was installed, and startup remained provider-free.

The corrected learning and independent baselines produced 226 recorded episodes across their stores (19 offline/reference), 1,400 model calls and 203 verified model traces. A provider connection failure, a request timeout, and three earlier rootless regression traces are preserved and explained. The $100 total ceiling was respected: $29.80986 conservative dispatched bound, $2.780649 estimated from known usage, actual billed dollars unavailable. No learned repair was accepted; Aria publication, protected audit and accepted-policy transfer remain unclaimed.

See [Phase 1 results](part2/PHASE1_RESULTS.md), [checklist](part2/PHASE1_TASKS.md) and [quick start](user-guide.md). The new GitHub Actions workflow runs the existing offline checks without credentials; remote CI execution is still pending a future push. Local services were idle at that checkpoint with results saved. No push or deployment was performed for Phase 1.


## Product continuation handoff — 2026-09-27

Documentation-only update: saved the owner's clarified product goal and continuation context in
[CURRENT_STATUS.md](../CURRENT_STATUS.md), [memory](../memory/context/product-continuation-2026-09-27.md)
and [the new-chat prompt](../NEW_CHAT_PROMPT.md). No application code, historical results,
credentials or experiments changed. No paid calls or GitHub push. The previous completed runtime
verification remains 1,952 backend passes / 180 existing skips, 166 frontend passes and a passing
production build; those suites were not rerun for this handoff. Checked local links, saved-source
contents, historical file preservation and HEAD/index preservation. Handoff verification and the
exact local checkpoint are recorded under `artifacts/product-continuation-2026-09-27/` and backed
up in a folder outside the repository on the team's machine.
