# Test triage (phase 1.10): where the time goes

Measured on 2026-10-11 in the cloud container (slower than the Mac; relative sizes are what
matter). The full backend suite is 3,840 tests; `tests/lab` alone is 1,085 of them and ran in
38 minutes (1,073 passed, 8 skipped) with `--durations`. The v2 suite (`tests/v2`, 120 tests) runs
in 30 seconds.

## The slowest files in `tests/lab` (call time summed per file)

| file | seconds |
|---|---|
| `test_heldout_check.py` | 294 |
| `test_completion_study.py` | 196 |
| `test_completion_evidence_reread.py` | 185 |
| `test_diagnosis_rules_loop.py` | 128 (one test) |
| `test_context_study.py` | 126 |
| `test_planned_agent_execution.py` | 120 |
| `test_original_loop_integration.py` | 112 |
| `test_reachability.py` | 84 (one test) |
| `test_lab_backoff_campaign.py` | 76 |
| `test_completion_manifests.py` | 67 |

The slowest single tests: the offline-fixture diagnosis campaign (128 s), the native planned
learning run (101 s), the reachability sweep over every caller (84 s), the lab back-off loop
(68 s), the original workflow with real worlds (64 s). Each is an end-to-end run of a whole
campaign through the real simulator and scheduler; they are the suite's integration tier.

## What a core suite under five minutes would be

Everything that is not an end-to-end campaign: contracts, kernel, effectsafe, packs, lab
runtime, oracle, evidence, adapters, incident evidence, the fast lab unit tests. The ten files
above plus the native-agent tests would carry a `slow` marker and run as their own CI job (they
already run as separate jobs for the experiment tier). This page is the measurement; the
marking is the rest of 1.10 and is a reviewed change to the legacy test tree, not done here.

Raw durations: produced with `pytest tests/lab --durations=80`; the log is not committed.
