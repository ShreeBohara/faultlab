# Phase 13 protocol — September 21, 2026

Phase 13 is the powered re-run of the protocol Phase 12 declared and could not execute:
[PHASE12_EXPERIMENT.md](PHASE12_EXPERIMENT.md). Phase 12 aborted on an external dependency
(W&B Weave ingestion at a 31% per-episode failure rate) and measured nothing.

**This file is transcribed from the frozen pre-run manifest, not authored after the run.**
Every value below is a field of `artifacts/phase13-2026-09-21/replay-manifest.json`, written
by `scripts/experiments/run_gate_replays.py` before the first paid call. It is recorded as a
separate document only because the declaration changed from Phase 12's; the reasoning behind
the design is Phase 12's and is not restated here.

## Declaration, as frozen in the manifest

| Field | Phase 12 | **Phase 13** |
|---|---:|---:|
| `policy_version` | `policy-d2b12ec1325742f5ac1428ec28f19639` | same |
| `scored_replays_declared` | 20 | **20** |
| `attempt_cap` | 28 | **30** |
| `spend_cap` | $160 | **$170** |
| `pass_verdict` | `OBSERVED_IMPROVEMENT` | same |
| `expected_actor` | `deepseek-ai/DeepSeek-V3.1` | same |
| `actor_context_protocol` | `faultlab-actor-context/v4-indexed-evidence` | same |

The attempt cap and spend guard rose because Phase 12 established that yield per attempt is
the binding cost, not per-episode price. Nothing else moved: the policy under replay, the
pass verdict and the actor are the same, so the read-out stays comparable to Phase 10's.

## Read-out

**Primary:** how many *scored* replays return `OBSERVED_IMPROVEMENT`, against Phase 10's
0 of 13 control. A replay that produces no validation assessment observed nothing about the
gate and is replaced, not scored.

**Declared target 20 scored replays.** If the 30-attempt cap arrives first, the shortfall is
reported as a shortfall — the figure is not quietly re-declared at whatever n was reached.

**Secondary, from Phase 12:** yield in scored replays per attempt, against the all-prior
baseline of 0.51 (Phases 10 and 11 pooled) and Phase 12's ~0.6 prediction.

## Pre-conditions actually enforced before dispatch

- `scripts/experiments/check_ingestion_health.py` must exit zero. It did, after a $4.70
  single-replay probe (`artifacts/phase13-probe/`) confirmed the Phase 12 degradation had
  cleared. The probe is counted in the shared ceiling and its own result is not a read-out.
- The runner aborts after 4 consecutive attempts with no validation assessment.
- The campaign is registered before polling, and the run aborts unless the started study
  echoes `replay_of`.
- Replay mode only: no Mechanic call, no proposal, nothing can be accepted.

## What must not happen

No gate change, no `checks.py` edit, no threshold move, no per-case exclusion, no resumption
of a stopped study, and no re-declaration of the read-out after seeing results.
