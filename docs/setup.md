# Setup record

Checked on 2026-09-12 on macOS. The original foundation record below is retained as
history; the implementation update at the end and integration-ledger.md describe current
verification. Team: Gatekeeper. Product: FaultLab. React evidence UI, FastAPI coordinator
and a separate private-world HTTP simulator run locally.

## Workspace

`faultlab/` was created beside `Brainstorm/`, `Hackthon_info/`, and `Idea_Planning_docs/`.
Those folders were left unchanged. There was no parent Git repository; only `faultlab/`
was initialized, with branch `main`.

The GitHub owner confirmed by the user is `ShreeBohara`. The created remote is the
private repository `https://github.com/ShreeBohara/faultlab`. GitHub authentication was
verified using the existing local login; no global Git configuration was changed.

## Tested tool and dependency versions

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

## Actual checks

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

The offline tests currently report an upstream Starlette/AnyIO deprecation warning;
it does not prevent health checks or tests from passing.

## Outstanding provider configuration

The user confirmed `WANDB_ENTITY=shreetbohara-quinstreet` and `WANDB_PROJECT=faultlab`.
These values are saved in local `.env`; they are not inferred from the Gatekeeper team
display name. Access to this entity and availability of hackathon credits have not been
verified yet. The user will enter `WANDB_API_KEY` directly in `.env` and confirm readiness.

From the repository root, after that confirmation:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet
```

Save an exact returned ID to local `WANDB_MODEL`. Only then run the explicit one-request
generation check:

```sh
./scripts/check-provider.sh wandb --generate --confirm-entity shreetbohara-quinstreet
```

Generation is limited to 32 output tokens and a 20-second request timeout, with SDK
automatic retries disabled. The script uses the same explicit entity/project for
inference attribution and Weave, and verifies the saved trace before claiming success.
Normal startup, the browser, health checks, and offline tests never call either service.
No live connection result or trace link is claimed in this record.

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

Frozen profiles: `offline-v1` is labeled offline deterministic smoke; `live-v1` requires
`FAULTLAB_LIVE_ENABLED=true`, a matching `FAULTLAB_CONFIRMED_ENTITY`, configured W&B
model/project/credentials and explicit Start. Provider budget maxima are 6000 model calls,
60M combined tokens and $100 if verified pricing exists. Unknown cost is not zero. The
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

Run `./scripts/setup.sh` to install the locked local dependencies. Start the simulator,
backend and frontend in three terminals with `./scripts/start-simulator.sh`,
`./scripts/start-backend.sh` and `./scripts/start-frontend.sh`; the UI is
http://127.0.0.1:5173. `./scripts/test.sh` runs backend tests, UI tests, build and browser
fixtures without providers. Browser tests use local Google Chrome when available; otherwise
install the local Playwright Chromium dependency with `cd frontend && npx playwright install chromium`.
With backend/simulator running, `cd frontend && FAULTLAB_BROWSER_LOCAL=1 npm run test:browser`
adds the actual local HTTP workflow. See README.md and docs/regression-runner.md for all
read-only export and explicitly enabled fresh-run commands.

Live campaign admission additionally requires verified nonnegative input/output pricing,
exact `FAULTLAB_PRICING_MODEL` match and `FAULTLAB_PRICING_VERIFIED=true`. Unknown pricing
blocks campaign admission; it is never interpreted as zero dollars. The separate one-request
provider compatibility check remains independently bounded. `openai/gpt-oss-120b` is the
initial candidate model, subject to account access and pricing verification; it has not been
called or established as available by this implementation session.
