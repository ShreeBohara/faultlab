# FaultLab — built by Gatekeeper

FaultLab tests an order-upgrade agent against real local HTTP faults, reproduces and reduces failures, tests diagnoses, and challenges generated recovery policies before fixed checks can promote them. The prototype, Explorer and Mechanic use W&B Inference in explicit live runs. A deterministic reference is available for offline smoke checks.

Implementation, offline evidence, live sponsor evidence and measured improvement have separate status in [the acceptance ledger](docs/integration-ledger.md). An installed loop is not evidence that a learned policy improves outcomes. No live campaign, learned-policy success, external transfer or Aria execution has been claimed from offline tests.

Start with the [short usage guide](docs/user-guide.md). The [live validation sequence](docs/live-validation.md) explains the remaining measured tasks and their commands.

To resume on another laptop or Codex account, read [CONTINUE_HERE.md](CONTINUE_HERE.md) and the linked detailed agent handoff before changing code or starting new runs.

## Start locally

Use Python 3.12, Node 20.19+ or 22.12+, and npm. From this repository:

```sh
./scripts/setup.sh
./scripts/test.sh
```

In three terminals:

```sh
./scripts/start-simulator.sh
./scripts/start-backend.sh
./scripts/start-frontend.sh
```

Open [FaultLab](http://127.0.0.1:5173). The simulator listens on localhost port 8001, the backend on 8000 and the frontend on 5173. Startup, health, page loads and tests require no credentials and make no paid calls. Use Ctrl+C to stop each server.

Run one explicitly labeled offline reference episode:

```sh
./scripts/run-demo.sh --mode baseline --wait
```

Copy its campaign ID to inspect or export persisted evidence:

```sh
./scripts/export-evidence.sh --campaign CAMPAIGN_ID --output artifacts/evidence.json
```

Exports and dashboard refreshes read recorded results. They do not replay business effects.

## Live configuration and execution

Keep credentials in the existing root `.env`; setup preserves it. Do not put secrets in frontend variables or commit them. Read [the sponsor setup walkthrough](docs/sponsor-setup.md) before enabling a live profile.

The current default is `deepseek-ai/DeepSeek-V4-Pro-0813` in canonical project `shreetbohara-quinstreet/Faultlab`. It passed real action, report, Explorer and diagnosis response checks with W&B's documented thinking toggle disabled. Healthy execution and the final 44-call learning attempt completed without provider errors, with all eight traces verified. That attempt finished `NO_CHANGE`; live automatic repair, challenge and promotion remain unverified. Use `./scripts/start-live-backend.sh` instead of the ordinary backend launcher; it preserves `.env` and sets matching prices and the $100 campaign cap. Restart any existing backend to load this configuration. Changing models requires matching verified prices and a new frozen campaign. See [model selection](docs/model-selection.md), [sponsor results](docs/sponsor-results.md) and [learning results](docs/learning-results.md).

```sh
# Offline installed-SDK compatibility only:
./scripts/check-provider.sh preflight

# Explicit W&B contact:
./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet

# One explicit bounded generation and Weave check:
WANDB_PROJECT=Faultlab WANDB_MODEL='deepseek-ai/DeepSeek-V4-Pro-0813' \
  ./scripts/smoke-sponsors.sh --confirm-entity shreetbohara-quinstreet \
  --max-output-tokens 2000

# Explicit fresh live campaign, after local configuration:
./scripts/run-demo.sh --mode learn --execute-live --wait
```

The preceding DeepSeek V3.1 campaign finished `NO_CHANGE`: 119 episodes, 829 model calls, zero provider failures and 119 verified episode traces. Its diagnoses remained inconclusive, so no repair qualified. Earlier Llama baseline measurements completed all 36 trials. These are retained results under their own models, not V4 results.

The learning loop may finish with no change, reject a candidate, or wait for verified Weave evidence. It never substitutes a canned repair or promotes on missing results. Aria setup is deferred for the current walkthrough and does not block Inference/Weave. Its later validation uses a supported W&B UI automation and attributed output capture; see [sponsor setup](docs/sponsor-setup.md).

## Components and evidence

- `backend/app/simulator`: four HTTP tools, private SQLite worlds, logical ticks, lost responses, delayed commits/rejections, historical reads and transient errors.
- `backend/app/referee`: fixed C1–C8, fresh-trial reduction, interventions, finite evidence-gap witnesses and immutable experiment freeze.
- `backend/app/lab`, `agents`, `adapters`: model roles, policy interpreter, journal, one-active-run controls and repeated evaluation.
- `backend/app/telemetry`: isolated Weave worker, durable outbox/readback, evaluation/dataset publication and W&B campaign bridge.
- `backend/app/integrations`: trusted regression runner and reviewed external-agent registration.
- `frontend`: task controls and persisted evidence drilldowns.

[Diagnostic evidence](docs/diagnostic-results.md) contains an actual finite committed/uncommitted witness and available-status control. It is a separately labeled fixture and excluded from learning gains. [External source review](docs/external-agent-setup.md) records the independently authored agent; successful transfer still requires the frozen external study.

See [demo instructions](docs/demo.md), [limitations](docs/limitations.md), [regression commands](docs/regression-runner.md) and [submission checklist](docs/submission-checklist.md). The repository is public by owner choice. Deployment and submission remain separate actions.

Earlier baseline measurements used Meta Llama 3.3 70B Instruct through W&B Inference. Built with Llama.
Offline tokenizer files and their license are recorded in `contracts/tokenizer/llama3/`.
