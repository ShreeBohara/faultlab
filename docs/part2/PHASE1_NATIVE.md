# Phase 1 native smolagents baseline

**September 20, 2026.** The native smolagents 1.26.0 `ToolCallingAgent` completed the planned 18-trial baseline: six public development cases, three fresh worlds per case, DeepSeek V3.1, and the unchanged empty baseline policy. All 15 scheduled faults triggered. The saved records show all 18 episode traces and the [Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0bfcf-38bd-74b2-941b-ac3b7a682ca4) verified.

This establishes execution and fault coverage for an independently authored agent loop. It does not establish an accepted repair or policy transfer. The agent produced eight completed tasks, eight violations and two safe unresolved outcomes; there were no recorded `LAB_ERROR` or interrupted episodes.

| Development case | Completed | Violations | Safe unresolved |
|---|---:|---:|---:|
| Healthy | 3 | 0 | 0 |
| Lost upgrade response | 3 | 0 | 0 |
| Delayed upgrade | 0 | 3 | 0 |
| Historical order | 2 | 1 | 0 |
| Terminal rejection | 0 | 3 | 0 |
| Transient notification failure | 0 | 1 | 2 |

## What failed

Five episodes exhausted their eight Actor calls without a valid original final report: all three delayed-upgrade trials, historical-order trial 1, and terminal-rejection trial 1. The recorded reason is `External agent produced no valid original final report`; the report remains null. The missing report fails C5–C7. The delayed and historical episodes had already completed both business effects, so their violations concern the required report. The terminal-rejection episode also sent a confirmation after a failed upgrade, violating C3.

The execution console reported malformed evidence IDs in rejected `final_answer` arguments for the three delayed-upgrade trials:

| Trial (one-based) | Rejected ID shown in console | Actual delivered ID |
|---|---|---|
| 1 | `evidence-1480dc13ba4947098108fc25极bd589` | `evidence-1480dc13ba4947098108fc25e18bd589` |
| 2 | `evidence-9ddfabe6d4a444369ff816极速c56319fe9` | `evidence-9ddfabe6d4a444369ff8166c56319fe9` |
| 3 | `evidence-0849dae734be433e极d3d817a86d6a0a` | `evidence-0849dae734be433e98d3d817a86d6a0a` |

These console excerpts were retained in the task conversation; the full stdout and raw native model replies were not saved to files. The other two missing reports cannot be assigned the same specific cause from the retained records alone.

All **13 successfully submitted reports cite only evidence IDs delivered in their episode**. Their reports match exactly across the submission event, persisted episode, root trace, verified evidence and evaluation prediction. All 18 root report/lifecycle values agree with their episode records, including the five null reports.

The other three violations are distinct:

- Terminal-rejection trials 2 and 3 sent a confirmation despite zero upgrade effects. Both reported `CORRECTLY_REJECTED` while claiming the notification succeeded, failing C3 and C5. Their evidence IDs were valid.
- Notification trial 3 submitted `notify-ff86e497882042c999704cd9bd1e41e` as its next operation, while the actual identity was `notify-ff86e4978820429c999704cd9bd1e41e`. This incorrect operation reference fails C7; its evidence IDs were valid.

## Attribution and limits

The reviewed adapter passes provider content into the native JSON parser, then validates the `final_answer` object without rewriting its IDs. The parser preserves string contents. An offline check using the three console examples confirmed that the parser preserves the malformed Unicode strings and `TaskReport` rejects them at the identifier constraint. The provider wrapper only replaces literal configured credentials with `[redacted]`; it has no substitution that creates these characters.

The evidence therefore supports malformed agent/model outputs reaching validation, with no observed adapter corruption. It does **not** prove the precise origin inside the upstream model/service: raw native generation messages and invalid proposal attempts were not persisted. The saved trace verification proves that recorded outputs and observations agree remotely; it does not reconstruct missing model messages. All 106 charged model calls have measured token usage, but this is not a general provider-reliability benchmark.

## Harness, provenance and accounting

The executed [tracked harness](../../scripts/experiments/native_baseline.py) matches the SHA recorded in this run. Relative to its original experimental copy, its only change resolves the existing simulator control capability **before** switching to the separate result directory. The earlier ordering selected a new capability file and failed readiness before any campaign, registration or episode was created. That zero-call first attempt remains in `artifacts/phase1-2026-09-20/native-baseline-1/`.

A temporary offline fixture confirmed that the fixed order reuses the original service capability without creating one in the new result directory; the old order produces a different capability. No real credential file or provider was used for this check.

The successful run used **106 model calls**, **424,709 input tokens** and **6,213 output tokens**. The ledger charged a conservative **$2.21540 ceiling**; the measured-token price estimate is **$0.2438414** at the frozen rates. Actual provider billing is unavailable.

Local evidence is under `artifacts/phase1-2026-09-20/native-baseline-2/`: `plan.json`, `summary.json`, `recording.json`, `telemetry.json` and `lab.sqlite3`. The campaign is `campaign-9581a7e140474e0889bb789c93b02f7d`; registration is `smolagents-1.26.0-6fed89323aea3bf5`. The recorded native source revision is `12c1bc820eca50ace6f80a21d90426d41d74f845`. Artifact directories are ignored by Git; these local recordings do not automatically accompany a public clone.
