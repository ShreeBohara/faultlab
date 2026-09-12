# FaultLab — built by Gatekeeper

The development foundation for our hackathon project. Product design and architecture are
still being brainstormed. This repository currently contains one React page, a FastAPI
health endpoint, and opt-in provider connection checks.

```text
frontend/       React + TypeScript + Vite
backend/        FastAPI, configuration, optional providers, offline tests
scripts/        Installation, start, test, and connection-check commands
docs/setup.md   Tested versions, actual check results, and remaining setup
```

## Install

Use Python 3.12 (tested with 3.12.8), Node.js 20.19+ or 22.12+, npm, and Git.
Vite's current requirements are in its [official guide](https://vite.dev/guide/).
No system-wide installation or upgrade is performed by this repository.

```sh
git clone https://github.com/ShreeBohara/faultlab.git
cd faultlab
./scripts/setup.sh
```

The repository is private; teammates need access granted by its owner before cloning.
Setup creates a project-local `.venv`, installs pinned Python dependencies and the npm
lockfile, and copies `.env.example` to `.env` only if `.env` does not exist.
If needed, select your installed Python explicitly:

```sh
FAULTLAB_PYTHON=/absolute/path/to/python3.12 ./scripts/setup.sh
```

## Run locally

In separate terminals, from the repository root:

```sh
./scripts/start-backend.sh
```

```sh
./scripts/start-frontend.sh
```

Open [FaultLab locally](http://127.0.0.1:5173). The page requests `/api/health`, which
Vite proxies to [the backend](http://127.0.0.1:8000/api/health).
Both servers bind to `127.0.0.1`. Startup and health checks do not need credentials
and never make model calls. Stop each server with Ctrl+C.

The scripts resolve their own repository location, so they also work when called by
absolute path from another directory. Equivalent direct commands are:

```sh
# From faultlab/backend:
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# From faultlab/frontend:
npm run dev
```

## Validate

```sh
./scripts/test.sh
```

This runs offline backend tests and the frontend TypeScript/production build.
Python's complete resolved dependencies are in `backend/requirements.lock`; direct
dependencies are recorded in `backend/requirements.txt`. npm uses `frontend/package-lock.json`.

## Configure W&B locally

Open the root `.env` in your local editor. Do not paste keys into chat, commit them,
or add provider credentials to frontend code or `VITE_` variables.
The backend loads this file by an explicit path; environment variables take precedence.

Set:

- `WANDB_API_KEY`: your W&B API key, entered locally.
- `WANDB_ENTITY`: the exact credited entity. The owner confirmed `shreetbohara-quinstreet`
  for this setup; access and credit availability still require verification.
- `WANDB_PROJECT`: `faultlab`.
- `WANDB_MODEL`: leave empty until model discovery returns a supported ID.

The blank template intentionally does not contain the owner's entity or any secrets.
W&B Inference uses `https://api.inference.wandb.ai/v1` with the W&B key and explicit
`entity/project` attribution. Weave uses the same key and project. See
[W&B's integration guide](https://docs.wandb.ai/weave/guides/integrations/inference).

Run these commands only when you intend to contact W&B and have confirmed the credited
entity. Model discovery makes no generation request:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet
```

Copy one returned model ID into `WANDB_MODEL` in `.env`. Then explicitly run a single
short generation check, which verifies that the selected model is still available:

```sh
./scripts/check-provider.sh wandb --generate --confirm-entity shreetbohara-quinstreet
```

The generation check uses a bounded timeout, a small output limit, no automatic
generation retries, and a real Weave trace. It reports sanitized failures and a trace
link when verified. This command consumes model usage; it is never called by the page,
health endpoint, setup script, or test suite. Successful access does not establish the
amount of promotional credit remaining; confirm that in W&B before further usage.

## TypeSafe

Status: **not configured — awaiting sponsor instructions**.

`TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`, and `TYPESAFE_MODEL` are reserved placeholders.
They do not assert an endpoint, authentication scheme, or compatible API protocol.
The optional module makes no requests until sponsor documentation is supplied and the
documented protocol is implemented. A status check is available with:

```sh
./scripts/check-provider.sh typesafe
```

## Working together

Open only `faultlab/` as the project folder in Codex. Read [AGENTS.md](AGENTS.md) before
coding. Keep the repository private during setup. Brainstorming and planning remain in
the untouched sibling folders and are not part of the application repository.

No agent loop, simulator, recovery policy, evaluation system, database, or product
dashboard has been implemented. Architecture decisions come next, after brainstorming.
See [the setup record](docs/setup.md) for verified checks and outstanding configuration.
