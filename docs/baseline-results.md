# Baseline results

**Live baseline comparison completed on 2026-09-13.** All 36 predeclared trials were valid, with no infrastructure errors. All 30 scheduled fault trials actually triggered their full recipes. The real model made two incorrect reports; these are measured agent failures, not application execution errors.

Model: `meta-llama/Llama-3.3-70B-Instruct`, JSON mode, temperature 0. Campaign `campaign-63933675566f49a994eb3e5bb6145434`; study `baseline-study-fdd60b0c85b5461fb97f76c5a804755d`; configuration `ac5674e4c9d83a0e57242a4637d296529b3532cfecf463f25b1eeb1746abe74c`.

| Arm | Trials | Completed orders | Correct rejections | Violations | Infrastructure errors | Scheduled faults triggered |
|---|---:|---:|---:|---:|---:|---:|
| B0 real Llama actor, empty policy | 18 | 13 | 3 | 2 | 0 | 15/15 |
| B1 handwritten reference, no model calls | 18 | 15 | 3 | 0 | 0 | 15/15 |

The six fixed development cases each ran three fresh trials per arm. They cover healthy execution, a lost upgrade response, delayed completion, a historical read, a terminal rejection, and temporary notification failures. Every attempt is retained. The two C5 violations occurred on temporary notification failures. No learned policy is claimed by this comparison.

Usage: 104 real model calls, 294,730 input and 4,149 output tokens; 167 total mock HTTP attempts across both arms. The conservative admitted inference ceiling is $0.7384, not a billed total. All 18 real actor episode traces were read back and verified. The [live Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09b7b-1890-78da-b9f9-1d7c162daf23) matched the fixed scores; B1 remains explicitly local-only.

Evidence: `artifacts/llama-baseline-study-final-20260913.json`. Reproduce the same declared study with `./scripts/run-baseline-study.sh --execute-live --wait` after starting the live backend. This starts a fresh paid study; it does not overwrite these outcomes.

## Earlier implementation evidence

# Baseline/reference development comparison

Status: measured acceptance PENDING.

The real HTTP reference test executed all six frozen development cases three times: 18 fresh worlds and zero model calls. All original B1 reports had no fixed-check failures; outcomes included completed, correctly rejected and truthful unresolved. This does not measure the competent model B0.

Required next evidence: Explicit priced W&B baseline/reference study with original model reports, valid/triggered counts and frozen configuration.

No provider calls were made for this report. See `integration-ledger.md` for software/offline verification and `limitations.md` for scope.
