# FaultLab — Gatekeeper

## Current scope

Implementation of FaultLab is authorized by the Step 2 request and the reviewed sibling
`FaultLab_Specs/HANDOFF.md` under constitution v1.1.0. Extend the existing skeleton.
LEAD owns shared contracts, configuration, dependencies, entrypoints, scripts and docs.
WORLD owns simulator/referee/audit; LOOP owns lab/agents/adapters; SPONSOR owns
providers/telemetry; UI owns frontend/src and frontend/tests; PORTABILITY owns integrations.
Follow `../FaultLab_Specs/specs/001-faultlab-loop/agent-assignments.md` for exact ownership.
The lead may maintain task progress and specifications in the sibling specification root.

## Workspace and privacy

- Application work belongs in `faultlab/`; authorized spec/task maintenance belongs in `FaultLab_Specs/`. Do not move or upload sibling folders.
- Inspect existing files and Git status before changing anything; preserve existing work.
- The user made `ShreeBohara/faultlab` public and authorized publishing this implementation,
  including its evaluation fixtures, to the existing `origin` remote. Keep that visibility;
  no additional visibility confirmation is needed when the user requests a push there.
  Confirm the owner before creating or switching to another remote. Do not deploy or enable paid overages.
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
