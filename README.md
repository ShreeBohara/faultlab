# FaultLab

**CoreWeave Hacks: Agent Loops · September 12–13, 2026 · San Francisco**

FaultLab is a bounded experiment lab for tool-using agents under injected HTTP faults. A weaker Actor tries a small business task. A stronger Explorer searches for failures. A fixed Referee scores the original report against private simulator truth. A Mechanic may propose a recovery policy. The lab promotes that policy only when repeated fresh trials prove it helps and does not break healthy behavior.

This is a **self-improving agent loop**, not weight training. The loop learns recovery policies around the model.

> **Try → Check → Repeat → Explain → Propose → Challenge → Promote**

## Why it exists

Timeouts do not mean failure. An order API can commit while the agent sees a lost response. Guessing creates duplicate effects or false claims. FaultLab studies whether an agent can stay truthful when the public evidence is incomplete.

The task is deliberately narrow: upgrade one mock order to express shipping, create exactly one confirmation, and report honestly. No real orders or email.

## The loop

| Stage | Who | What happens |
|---|---|---|
| Discover | Explorer + Actor | Inject a fault. Attempt the task in a fresh world. |
| Check | Fixed Referee (C1–C8) | Compare the Actor's report with private simulator truth. |
| Reproduce | Lab | Repeat the same failure in three fresh worlds. |
| Reduce | Lab | Search for a smaller recipe that still fails. |
| Diagnose | Mechanic + fixed tests | Policy gap, contract evidence gap, or inconclusive. |
| Propose | Mechanic | A constrained recovery-policy candidate, or honest no-change. |
| Challenge | Explorer as adversary | New fault schedules try to break the candidate. |
| Promote | Fixed comparisons | Accept only measured improvement that preserves healthy behavior. |

`NO_CHANGE` is a valid scientific result. The lab will not promote an unsupported repair.

## Roles and models

Live campaigns split the models on purpose:

- **Actor** (system under test): `meta-llama/Llama-3.1-8B-Instruct`
- **Explorer / Mechanic** (lab helpers): `deepseek-ai/DeepSeek-V4-Pro-0813`
- **Referee**: fixed code, never a model

Each campaign freezes this role map and bills each role at its verified price.

## Sponsor tools

| Tool | How FaultLab uses it |
|---|---|
| **W&B Inference** | Hosted models for Actor, Explorer, and Mechanic. Bounded calls, no retries, JSON mode. |
| **Weave** | Eligible live episode traces are saved, read back by exact identity, and matched to local evidence before they can justify later optimization. |
| **Aria** | After a campaign finishes, FaultLab publishes a W&B run named `faultlab-campaign-<id>`. A Finished-run automation asks Aria for one advisory summary. Aria does not score episodes or promote policies. |

Required for a live run: a W&B API key in the root `.env`. Do not put secrets in frontend code or commit them.

## Quick start (offline, no credentials)

Python 3.12, Node 20.19+ or 22.12+, and npm:

```sh
./scripts/setup.sh
./scripts/test.sh
```

Three terminals:

```sh
./scripts/start-simulator.sh    # :8001 mock order APIs
./scripts/start-backend.sh      # :8000 coordinator
./scripts/start-frontend.sh     # :5173 dashboard
```

Open http://127.0.0.1:5173. Startup and health checks make no paid calls.

One offline reference episode:

```sh
./scripts/run-demo.sh --mode baseline --wait
```

## Live demo (W&B)

1. Copy `.env.example` to `.env` and set `WANDB_API_KEY`, `WANDB_ENTITY`, and `WANDB_PROJECT`.
2. Create a Finished-run Aria automation on that project (`^faultlab-campaign-.*`, action **Trigger ARIA**, exact prompt from `backend/app/telemetry/aria_bridge.py`).
3. Follow **[docs/hackathon-demo.md](docs/hackathon-demo.md)** for the one-campaign run.

```sh
set -a && source .env && set +a
./scripts/start-simulator.sh
./scripts/start-live-backend.sh
./scripts/start-frontend.sh
```

Create a **Learn** campaign in the dashboard, then click **Start campaign**. Do not reopen an old campaign after changing `WANDB_PROJECT`. Skip the smoke check if you want Weave to contain only this campaign's traces.

## What judges should look at

1. **Run summary** — which stages ran, and which were not reached.
2. **Evidence timeline** — original Actor report vs Referee verdict.
3. **Reproduce / Diagnose / Challenge** — only for stages that actually executed.
4. **Sponsor evidence** — verified Weave traces and captured Aria output.

A recorded live split-model campaign finished `NO_CHANGE` after a repeatable C5 truthful-report failure and an inconclusive diagnosis. That is the honest outcome: the loop found a scar, refused to invent a fix, and kept the evidence.

## Architecture

- `backend/app/simulator` — local HTTP world, four ordinary faults (delay, pending, stale read, transient failure)
- `backend/app/referee` — fixed C1–C8 checks
- `backend/app/lab` — campaign state, budgets, learning stages
- `backend/app/agents` — Actor, Explorer, Mechanic
- `backend/app/telemetry` — Weave outbox/readback and Aria campaign bridge
- `frontend` — dashboard over persisted records only

Longer explanation: [docs/demo-guide.md](docs/demo-guide.md). Limitations: [docs/limitations.md](docs/limitations.md).

## License and provenance

Built at CoreWeave Hacks (Agent Loops) with Weights & Biases Inference, Weave, and Aria. Offline Llama tokenizer files and license are in `contracts/tokenizer/llama3/`.
