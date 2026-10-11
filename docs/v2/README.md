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
| Belief-versus-effect oracle v1 | `faultlab/referee/oracle` | `ORACLE.md` | 144 of 144 agreement with recorded C5/C6 on the Claude screen |
| effectsafe 0.1 alpha | `effectsafe/` | `EFFECTSAFE.md` | the non-idempotent create, same-bytes resend and no-decay tests |
| Providers beyond W&B, verified prices, monthly ledger | `backend/app/providers` | `../providers.md` | live smoke and the four-model screen |
| First multi-provider data | runs folder | `../CLAUDE_ACTOR_SCREEN_2026-10-11.md` | 72 live episodes, four models |

Tests for the new packages live in `backend/tests/v2` and run with the core suite
(`./scripts/test.sh backend`).

## Not there yet (Stage 1 remainder)

Task-pack interface with the orders checks moved verbatim (1.3), the trial worker and typed
store (1.5), one adapter interface and registry (1.6), the CLI, pytest plugin and CI action
(1.7), incident bundles v2 and replay (1.8), the rest of the oracle (free-text extraction,
calibration), the rest of test triage (a core suite under five minutes), exporters with Weave
optional (1.11), docs v2 (1.12). The legacy loop still runs the research path on
`backend/app`.
