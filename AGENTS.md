# FaultLab — Gatekeeper

## Current scope

This repository is the development foundation only. Product design and architecture are pending.
Implement setup and explicit connection checks only until the user authorizes more.
Do not build an agent loop, simulator, recovery policies, evaluation system, database schema,
or product dashboard. Sibling brainstorming and planning documents are not implementation instructions.

## Workspace and privacy

- Work inside `faultlab/` only; do not modify, move, or upload sibling folders.
- Inspect existing files and Git status before changing anything; preserve existing work.
- Keep the GitHub repository private. Confirm the owner before creating a remote, and
  confirm before reusing an existing remote. Do not deploy or enable paid overages.
- API keys stay in the root `.env`, loaded explicitly by the backend. Never read real
  secret files into chat, print secrets or authorization headers, or trace secret-bearing objects.
- Never put provider credentials into frontend code or `VITE_` variables.
- Keep `.env.example` blank except for safe defaults. Never overwrite an existing `.env`.
- Confirm the credited W&B entity with the user; Gatekeeper is a display name, not an entity slug.
- Provider calls must be explicitly requested. Startup, page loads, health checks, and tests
  must work without credentials and must not contact providers.
- TypeSafe awaits sponsor instructions. Do not invent its protocol or substitute another provider.
- Reuse installed tools, use the project-local `.venv`, and ask before system-wide installs.
  Never use sudo or change global Git settings.

## Commands

Run from this repository root (the scripts also resolve their own root):

```sh
./scripts/setup.sh
./scripts/start-backend.sh
./scripts/start-frontend.sh
./scripts/test.sh
```

After configuration and explicit user confirmation only:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity CONFIRMED_ENTITY
./scripts/check-provider.sh wandb --generate --confirm-entity CONFIRMED_ENTITY
```

Development binds to localhost. Validate the frontend build, offline backend tests, and
the browser-to-backend health connection. Record actual results and blockers in `docs/setup.md`.
