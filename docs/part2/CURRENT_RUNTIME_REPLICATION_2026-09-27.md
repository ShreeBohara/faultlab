# Current-runtime replication — September 27, 2026

**Declared before execution.** The owner authorized the lead to choose and perform the next
bounded work. This document defines one public development measurement. Launch still requires
passing offline checks and an external freeze record matching the finished runner and runtime.
It records no result and authorizes no repeat of a completed or interrupted run.

## Question and scope

Does one previously generated upgrade repair still behave as expected on its seven public
development cases after the September 27 software corrections?

This is **existing-policy software compatibility measurement**, not learning, an unseen-case
check, new certification, promotion or evidence that a policy should be activated. No Explorer
or Mechanic is called. The Phase 30 report-status hint remains unadopted. No protected partition
is opened, sampled, served or used for selection. C1–C8 and the interpreter remain unchanged.
The simulated shop retains its original request de-duplication. Successful retries here do not
establish safety against a service that can apply the same request twice. This public case set
also contains no notification-side fault, so it cannot establish the safety of notification rules.

Phase 28's protocol prohibited further candidate retesting and held-out routing within its
declared experiment (§14), and restricted its results to development evidence (§13). This new,
separately named measurement deliberately reuses an old policy to check **changed software**;
it is not a continuation, second chance or amendment of Phase 28. Its outcomes cannot revise
Phase 28's 9/49 count, decisions, pins or restrictions. An old policy that behaves differently
here keeps its original historical result. The new record carries both runtime identities.

## Binding selection and cases

Select the **first strongly qualified Phase 28 attempt, attempt 5**, by saved attempt order,
before making any new call. Do not choose by apparent simplicity, current outcomes or hash order.

- Original campaign: `campaign-ba37f75678284372ad5dcc2b3635481e`.
- Original study: `completion-study-a0c535bb041c413da1d4b34fb513252c`.
- Exact policy hash: `04721232187d99677e698ce59b45ccd76ad2cb7c43854eff4c6a1e46163c548c`.
- Policy version: the exact `selected_candidate_version` in that study; record it in the freeze.
- Baseline: empty `policy-v0`, hash
  `bafdc14f280cd47441baf69006e8ca55885ca0349667f2695f57e40b3b8926fb`.
- Selection source: `artifacts/phase28-2026-09-26/upgrade-loop-manifest.json`. Check its attempt,
  study, campaign, certification and policy identity against the saved study and policy content.
  Do not select a different same-hash policy record or turn `OBSERVED_IMPROVEMENT` alone into
  strong qualification. Missing or inconsistent source evidence refuses launch.

Use `build_case_manifest('upgrade-v1')` unchanged, with complete manifest hash
`cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3`.
All cases use `standard-v1` and scope `orders.upgrade_then_confirm/v1`. Each nonempty fault
targets `orders.update_order` at occurrence 1. Order and identities are fixed:

| Case | Seed | Public fault | Expected task outcome |
|---|---:|---|---|
| `healthy` | 101 | None | `COMPLETED` |
| `upgrade-3` | 703 | F4, 3 transient failures | `COMPLETED` |
| `upgrade-2` | 702 | F4, 2 transient failures | `COMPLETED` |
| `delayed-upgrade` | 103 | F2, 3 ticks, `SUCCEEDED`, null failure code | `COMPLETED` |
| `upgrade-18` | 718 | F4, 18 transient failures | `SAFE_UNRESOLVED` |
| `lost-upgrade-response` | 102 | F1, response delay 1,500 ms | `COMPLETED` |
| `terminal-upgrade-rejection` | 105 | F2, 2 ticks, `FAILED`, `UPGRADE_REJECTED` | `CORRECTLY_REJECTED` |

Run three pairs per case: **21 pairs, 42 planned episodes** in fresh independent worlds.
Each pair runs B0 (empty baseline) and L (the frozen saved policy). Use the existing
`PairedEvaluator` order: B0 then L when `(case_index + trial_index)` is even, otherwise L then B0.
Store case, pair, arm, episode, world and policy identities before or as each attempt starts.
Do not send these results back to a proposer or select another policy if the result disappoints.

## Runtime, prices and spending

Use the corrected current runtime with Actor `deepseek-ai/DeepSeek-V3.1` and context
`faultlab-actor-context/v4-indexed-evidence`. Preserve the existing Actor prompt, response
protocol and episode caps, including at most eight Actor turns per episode. The existing blind
transport retry does not consume another turn, so there may be up to sixteen charged provider
attempts per episode. The v2
task-outcome evidence summary may be recorded as configuration; no Mechanic consumes it here.
W&B destination remains `shreetbohara-quinstreet/Faultlab`. Credentials stay in the local `.env`.

The lead verified the exact-model published prices for this declaration:

| Role/model | Input / output dollars per million tokens | Use in this run |
|---|---|---|
| Actor, DeepSeek-V3.1 | $0.55 / $1.65 | Actor calls only |
| Configured Explorer/Mechanic, DeepSeek-V4-Pro-0813 | $1.31 / $3.96 | Zero calls |

Sources: [W&B V3.1 pricing](https://wandb.ai/site/inference-model/deepseek-v3-1/),
[W&B available models](https://docs.wandb.ai/inference/models), and
[W&B V4-Pro-0813 pricing](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/).
Save the pricing verification with the freeze. A mismatch or unavailable model aborts admission;
do not substitute a model or silently restore old prices.

At caps of 32,000 input and 2,000 output tokens, the Actor per-call conservative bound is
`(32000 × 0.55 + 2000 × 1.65) / 1000000 = $0.0209`.
The fixed batch allows 42 episodes × 8 Actor turns × at most 2 transport attempts per turn:
**672 charged calls maximum, $14.0448 worst-case bound**. Whole-pair `LAB_ERROR` retries are
disabled (`allow_lab_retry=False`). Every actual provider attempt must fit the charged call
and token limits; there is no extra unmetered SDK retry allowance. Allowing both transport and
whole-pair retries would exceed this declaration and is inadmissible.

The phase cap is **$20 conservative charge**, not a spending target. Bind the campaign ledger
and phase admission checks to that cap and the 672-call ceiling. Only Actor calls may be made;
do not add paid model discovery or smoke calls outside this accounting. Start only when the
whole declared worst case fits. The shared carried balance is $811.70 charged / $188.30 remaining
of $1,000 before this run. Debit actual conservative charges afterward; no budget increase or
reclaim of historical rounding is needed. Report provider-billed dollars as unknown if unavailable.

## Freeze and execution

1. Preserve a local source/evidence backup. Complete the full backend suite and focused new-runner
   tests with no unexplained failures; retain legitimate archive skips and their reasons. Save
   the check outputs. Do not edit old runners or result files to make this run admissible.
2. Finish this protocol and the runner. Create a preparation directory named for this replication,
   outside all `phase28-*` folders. Save the public manifest, exact policy snapshot, plan and
   non-secret settings there. The execution output directory is a **different, never-existing
   path**; for example a common parent may contain `preparation/` now and `run/` only at launch.
   Preparing a freeze must not create the execution output directory. The runner creates that
   directory exclusively and refuses an existing one, including a partial prior run.
3. Write an **external freeze record** containing the final protocol and runner file hashes,
   current configuration/runtime/algorithm/scorer/interpreter/prompt/contract/dependency hashes,
   source study's original configuration hash, manifest hash, policy identity, budgets, pricing
   evidence and test-result references. Keep this freeze in the preparation directory, outside
   the execution output directory. Never put a file's own hash inside itself. All required
   pins must match at admission; create a fresh campaign in a new isolated store on the new
   configuration. Read the historical source database read-only. Never repin an old campaign
   to the new software. Copy only the identities/content required for the fixed comparison.
4. Confirm no fresh execution is active. Keep the dashboard closed and the ordinary backend
   stopped during the isolated runner's work. The simulator must run from the frozen checkout
   with `--timeout-keep-alive 75`. Reserve the ordinary backend port 8000 during the isolated
   execution so another backend cannot start unnoticed. Check health without provider calls.
   Use the project `.venv`.
5. Execute once. Refuse any changed pin, invalid identity, budget/pricing mismatch or unexpected
   active execution. Do not weaken a refusal, overwrite an output directory or resume the run.
   A report may be reconstructed read-only from saved evidence after interruption; this starts
   no trials and changes no existing verdict. The standalone ledger may release only its own
   unused generic audit/portability/selector reservations, since those activities never run here;
   do not release reservations in the main store. An Actor-only provider wrapper must reject
   every other role, and the isolated ledger's call-price bound must be the verified Actor rate.

## Stops, retries and readout

Run the complete fixed batch even if an early task outcome is disappointing. Do not stop at a
success or continue past the declared batch. An external stop, lost integrity, changed runtime,
budget exhaustion or unrecovered infrastructure error ends execution and retains all attempts.
Whole-pair retries are disabled. Retain the existing Actor's **one blind transport retry only
when no generation arrived**, within the same episode and charged to the limit. Preserve the
failed transport attempt in evidence. Model report errors, returned content/format failures,
rule failures, ordinary unresolved tasks and untriggered faults are not retry reasons. Any
candidate C1–C8 failure remains prominently reported; no later answer substitutes for it.
The existing Actor may give format feedback within its original eight-turn episode budget;
this unchanged behavior does not authorize another episode, pair or unmetered repair call.

Publish per-case and per-arm outcomes, failed checks, scheduled/triggered faults, pair completeness,
actual policy steps and dispatched retries, charged calls, conservative cost and evidence-readback
status. Missing or invalid required pairs mean an incomplete measurement. Keep execution integrity,
task completion and report correctness separate. A clean run is not a new acceptance threshold.

Verify evidence manually after execution, including exact episode/world/HTTP-attempt identities,
selected model outputs and their cited observations, actual shop effects and saved Weave readbacks.
Run the clock/attempt-count/masked-fault check with explicit store and worlds paths and required
world files. **A zero-episode scan is not verification.** For a clean run reconcile exactly 42
planned episodes/worlds; also enumerate every charged transport retry within those episodes.
There must be no additional pair-retry episodes. For an aborted
run reconcile the actual attempted identities and explicitly list missing planned trials. Require
nonzero checked coverage, no unexplained missing world, and agreement with the runner's records.
Report drift or masked faults as lab defects; do not erase, correct or rerun affected outcomes.

Finish with a separate results artifact and updated current status/budget. Preserve this protocol,
its freeze and every prior phase report. The conclusion must say that this is one frozen repair
on known public cases under a new runtime: no unseen generalization, new learning, causal harm
claim, original `ACCEPTED` result or policy activation follows from it.
