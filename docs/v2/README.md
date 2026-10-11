# FaultLab v2: what exists so far

The plan (October 2026) rebuilds FaultLab into three products on one engine: the **lab** that
proves what an acting agent actually did, the **bench** that ranks agents on it, and
**effectsafe**, the runtime layer that enforces it. The rebuild is a strangler refactor: new
packages beside the legacy `backend/app`, which stays importable and keeps every historical
store readable. This page lists the pieces that exist, each with its evidence.

| Piece | Where | Doc | Evidence |
|---|---|---|---|
| Core vocabulary (canonical JSON, digests, ids, caps) | `faultlab/core` | `EVIDENCE.md` | identity byte-identical to the legacy lab (tests) |
| Trial envelope and the legacy projection | `faultlab/evidence` | `EVIDENCE.md` | 6,667 of 6,667 archived episodes project |
| World kernel and the orders pack | `faultlab/env/kernel`, `faultlab/packs/orders` | `KERNEL.md` | the 20 simulator tests pass against it; a foreign pack runs on it |
| Task-pack interface, registry and `packs` command | `faultlab/packs` | `PACKS.md` | orders parity with the legacy manifest, hooks, tools, report schema and checker digest (tests) |
| Typed trial store, scheduler, worker, session, kernel transport | `faultlab/lab` | `LAB.md` | all six orders scenarios run to sealed envelopes on the kernel through effectsafe (tests) |
| Legacy orders referee behind the v2 `Referee` protocol | `faultlab/referee/legacy.py` | `LAB.md` | C1 to C8 pass on every scenario for the scripted agent; a false success claim is a violation (tests) |
| Adapter interface, the deterministic reference adapter, registry, `run` command | `faultlab/adapters`, `faultlab/lab/cli.py` | `ADAPTERS.md` | the reference adapter passes C1 to C8 on every scenario; `faultlab run` to sealed envelopes (tests) |
| pytest plugin and the CI smoke job | `faultlab/testing/plugin.py`, `.github/workflows/ci.yml` | `TESTING.md` | a clean run passes, a lying agent fails with every problem listed (tests); CI runs the offline batch |
| Replay: recorded inputs in a fresh world, divergence stop, cut points | `faultlab/lab/replay.py` | `EVIDENCE.md` | a replay reproduces the recorded run; a different world stops at the first divergence (tests) |
| Belief-versus-effect oracle v1 | `faultlab/referee/oracle` | `ORACLE.md` | 144 of 144 agreement with recorded C5/C6 on the Claude screen |
| effectsafe 0.1 alpha | `effectsafe/` | `EFFECTSAFE.md` | the non-idempotent create, same-bytes resend and no-decay tests |
| Providers beyond W&B, verified prices, monthly ledger | `backend/app/providers` | `../providers.md` | live smoke and the four-model screen |
| First multi-provider data | runs folder | `../CLAUDE_ACTOR_SCREEN_2026-10-11.md` | 72 live episodes, four models |

Tests for the new packages live in `backend/tests/v2` and run with the core suite
(`./scripts/test.sh backend`).

## Not there yet (Stage 1 remainder)

Moving the orders checks themselves out of the legacy referee (the rest of 1.3; the pack pins
their digest and the worker leaves the task outcome pending until a referee exists), an HTTP
transport for the worker (the rest of 1.5), the model-backed, native and local adapters (the rest
of 1.6), the rest of the CLI and a reusable CI action (1.7), the rest of the oracle (free-text
extraction, calibration), the rest of test triage (a core
suite under five minutes), exporters with Weave optional (1.11), docs v2 (1.12). The legacy loop
still runs the research path on `backend/app`.
