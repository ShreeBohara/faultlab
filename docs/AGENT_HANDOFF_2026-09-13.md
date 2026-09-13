# FaultLab: detailed continuation handoff

Snapshot date: **2026-09-13**. This document describes the completed validation
session and accompanies the subsequent source publication. Verify actual files/state
on arrival; later user instructions and later evidence take precedence.

## 1. Read this first

The app executes a real model against local synthetic order APIs and records
verified Weave evidence. Healthy order execution works. The latest live learning
attempt completed without provider errors, but found no fixed-rule violation.
It therefore ended `NO_CHANGE`, retaining `policy-v0`.

**The central unverified milestone is automatic generated repair through source
validation, challenge and promotion.** These paths are implemented and covered by
offline tests, but were not exercised successfully as one live learning cycle.
Do not describe this as a fully proven self-repairing product.

The user is frustrated by extended implementation and repeated partial completion
claims. Their priority is the promised existing workflow, not perfection or new
features. They want simple explanations, concrete progress in `tasks.md`, actual
API execution, and an easy guide explaining why each step exists and what the
frontend/backend do. Do not restart the entire project or keep changing models
without a specific, evidence-based reason.

At handoff: **116/121 task checkboxes checked**, five measured gates open. There
was **no active campaign**. The local services were left available, and the UI
showed the final campaign. Processes do not transfer to another laptop.

## 2. Locations, Git state, and what must survive the move

Original parent: `/Users/shree/Desktop/Coreweave_AGI_Hackthon`.

| Location relative to the parent | Purpose |
|---|---|
| `faultlab/` | Application repository and working tree |
| `FaultLab_Specs/` | Authoritative specs, task progress, constitution and local Spec Kit skills |
| `faultlab/artifacts/` | Ignored local runtime/evidence: SQLite, worlds, exports, probes, logs and source-review material |
| `faultlab/.env` | Existing local credentials/settings; preserve privately, never print or overwrite |

Public remote: `https://github.com/ShreeBohara/faultlab.git`, branch `main`.
Base commit before this source update: **`d32aa55`**. The preceding requested four-commit
push was completed before the latest validation fixes:

1. `f78efa7` — simulator, contracts and learning engine.
2. `fa666f6` — live inference, verified Weave and sponsor workflows.
3. `a1a239a` — dashboard and evidence inspection UI.
4. `d32aa55` — operator scripts, guide and then-current live results.

**This source update includes the subsequent code/docs fixes, tokenizer assets and
handoff files.** Use the updated `main`, not the older `d32aa55` snapshot. Start with
`git status --short` and `git diff --stat`; preserve any later local changes. Never
run `git reset --hard` or `git clean` to make this handoff look clean. The accompanying
[working-tree inventory](handoff-working-tree-2026-09-13.txt) records the historical
state before these commits, not the current Git status. Credentials, ignored local
campaign artifacts, and sibling specifications still require a separate private transfer.

The user made this repository public and explicitly requested that fact in
`AGENTS.md`; it is already recorded there. Do not infer privacy from the historical
commit title “Record verified private GitHub setup.” Do not change visibility,
remote owner, publish sibling specs, deploy, or enable paid overages.

For continuity, retain the whole `artifacts/` directory, especially:

- `lab.sqlite3`: campaign, episode, policy, budget, trace and evidence records.
- Its `-wal` / `-shm` files when copying a live SQLite database; a bare main-file
  copy while a server is writing is not a safe database snapshot.
- `worlds/`: per-world simulator SQLite files, and local control material.
- All named evidence exports and probe records listed below.

Stop writers before a filesystem copy, or use SQLite's backup API for a consistent
database snapshot. Do not run two backends against one shared artifact directory.
Keep runtime artifacts and control capabilities private; they are deliberately
ignored by Git. Weave links alone do not replace the local authoritative records.

Copied virtual environments may contain absolute paths or incompatible binaries.
On a different laptop, create a fresh project-local Python 3.12 environment from
the lockfile if needed; do not change dependency versions merely to get a clean
install. The guide's old absolute `cd` path must be adapted to the new location.

## 3. Reading order and authority

Do not ingest every historical file blindly. Read in this order:

1. Application `AGENTS.md`: scope, privacy, ownership, offline/provider controls.
2. This handoff and `../FaultLab_Specs/specs/001-faultlab-loop/tasks.md`: current
   checked items, open definitions, and Phase 16 entries near the end.
3. `docs/learning-results.md`, `docs/model-selection.md`, `docs/sponsor-results.md`
   and `docs/baseline-results.md`: actual measurements and retained failed attempts.
4. `docs/user-guide.md`: current operator walkthrough; Word counterpart is
   `docs/FaultLab_Quick_Start_Guide.docx`.
5. `../FaultLab_Specs/HANDOFF.md`, then the feature's `spec.md`, `plan.md`,
   `experiment-protocol.md`, `evaluation-plan.md`, and relevant `contracts/` files.
6. `docs/integration-ledger.md`, `docs/limitations.md`, and the code map below.

The original `../FaultLab_Specs/IMPLEMENTATION_START_HERE.md` explains the initial
Step 2 request. It is historical: its “104 unchecked tasks,” “future work,” and
initial no-live-authorization language do not describe the final state. Do not
rerun initial setup/planning or recreate the task list based on those sentences.
Dated older sections in other docs are also retained history, not fresh results.
Current checkboxes and exact saved campaign evidence take precedence over a stale
summary sentence. No checkbox or assistant message proves a measurement by itself.

Spec Kit is installed in the sibling specs directory. If an implementation task
requires it, read `.agents/skills/speckit-implement/SKILL.md` there. Run prerequisite
checks from **the specs root**, not the application root:

```sh
.specify/scripts/bash/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks
```

Application commands run from **the application root**. Do not run `specify init`
or regenerate `spec.md`, `plan.md`, or `tasks.md`. Add only traceable real gaps when
required; retain original task definitions and evidence gates. Current Codex
instructions govern whether delegation is available; no prior worker is required
to continue this project.

## 4. Product architecture in plain terms

FaultLab tests an agent doing one supported task: **upgrade a synthetic order to
express shipping, then send one truthful simulated confirmation**. It does not
send real email or operate a production order system. It learns a constrained
recovery policy around an agent; it does not train the model's weights.

```text
Browser dashboard → FastAPI coordinator → agent → mock HTTP order/notification APIs
                              ↓                         ↓
                       saved local evidence ← fixed Referee checks C1–C8
                              ↕
                         Weave upload/readback
                              ↓
 Explorer chooses faults → reproduce → reduce → test diagnosis → Mechanic policy
                              → paired source checks → challenge → promotion
                              → policy/regression persistence when eligible
```

- **Actor / B0:** the real model performing the task with an empty recovery policy.
- **B1:** a handwritten reference used for comparison, not a learned policy.
- **L:** the same model and base settings with a candidate/accepted recovery policy.
- **Explorer:** proposes one or two allowed fault primitives, later challenges a policy.
- **Mechanic:** proposes a diagnosis and, only when eligible, a constrained policy.
- **Referee:** fixed code checks original reports against actual effects and delivered
  evidence. It is not an LLM judge and cannot be rewritten by the candidate.

Ordinary fault primitives: F1 lost/late response after commit; F2 delayed terminal
upgrade completion; F3 a real older order projection; F4 pre-effect transient
failure. A scheduled fault is not necessarily triggered. A whole recipe must
actually trigger before it can establish failure/recovery evidence.

`SAFE_UNRESOLVED` and `CORRECTLY_REJECTED` can be valid truthful outcomes. They do
not automatically indicate a policy bug. `NO_CHANGE` is a completed campaign with
no accepted new policy. Infrastructure `LAB_ERROR` is separate from a business
invariant failure. A model response, generated candidate, passing pair and accepted
policy are different milestones.

## 5. Current model, SDKs, credentials and spend

| Setting | Verified configuration at handoff |
|---|---|
| W&B entity | `shreetbohara-quinstreet` |
| Canonical project | `Faultlab` (capital F); full path `shreetbohara-quinstreet/Faultlab` |
| Model | `deepseek-ai/DeepSeek-V4-Pro-0813` |
| API base | `https://api.inference.wandb.ai/v1` |
| Model-specific option | `extra_body={"chat_template_kwargs":{"enable_thinking":false}}` |
| Campaign output settings | JSON object, temperature 0 |
| Per-call admission | 32,000 input + 2,000 output tokens; 20-second timeout; zero SDK automatic retries |
| Campaign ceilings | 6,000 calls, 204,000,000 tokens, $100; also eight discovery selections/four candidate attempts |
| Verified rate snapshot | $1.31/M input and $3.96/M output tokens |
| Conservative per-call dollar reserve | $0.04984 |

The 2K output ceiling is not a new user constraint. The user said tokens were not
the concern; disabled-thinking probes fit comfortably, so there was no observed
reason to raise it. Required proposal input did exceed the old 8K allowance, which
was increased coherently to 32K. If a new real prompt exceeds current admission,
preserve it and investigate; do not truncate away contradictory trials or merely
raise a constant without updating reservations, schemas and frozen configuration.

Official sources checked during validation (recheck if later changed):

- [W&B Models quickstart](https://docs.wandb.ai/models/quickstart): experiment tracking,
  not the hosted inference model catalog.
- [Available inference models](https://docs.wandb.ai/inference/models).
- [Reasoning settings](https://docs.wandb.ai/inference/response-settings/reasoning):
  this exact V4 model enables thinking by default and documents the disabling flag.
- [V4 Pro 0813 model/pricing](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/).

Selection was based on real request compatibility and the documented capabilities,
not a universal “best model” benchmark. See `docs/model-selection.md` for comparisons.
Do not send the V4-only flag to V3.1 or other models without documented support.

`scripts/start-live-backend.sh` applies non-secret model/project/pricing overrides
while preserving the actual `.env`. The `.env` can still contain an older model;
running the ordinary backend or a standalone CLI without the same overrides may
therefore select different settings. Verify `/api/config/status` and the frozen
campaign receipt. External registration CLI settings also need explicit checking;
an environment exported inside the backend process is not inherited by another
terminal. Never print `.env` or the complete settings object to debug this.

Important pins: Python 3.12; `openai==3.13.0`, `weave==0.53.9`, `wandb==0.30.0`,
`tokenizers==0.23.2`, `pydantic==2.13.5`, `fastapi==0.141.1`,
`smolagents==1.26.0`. Use `backend/requirements.lock` and
`frontend/package-lock.json`; the old machine used Node 20.19.0/npm 10.8.2.

The user authorized model discovery, smoke checks and a full live learning cycle
within $100, and explicitly deferred Aria. They said additional credits were
possible; that is not permission to enable overages or silently exceed the cap.
W&B credentials are independent of the Codex account. Do not assume a different
Codex account grants a different W&B entitlement or a fresh budget.

Read-only ledger snapshot at handoff: 12 live campaigns, **1,363 model calls**,
4,232,175 recorded input and 82,879 output tokens, and **$27.47594 in conservative
admitted inference ceilings**. Two old calls have unknown token usage. These
totals exclude standalone compatibility/smoke probes and unrelated account work;
they are not a billing receipt or an exact remaining account balance. Every
campaign cap is per campaign, not a shared account/session cap. Account billing
and unledgered probes must be considered before further spending.

Protected capacity remains reserved: 384 final-audit calls, 288 portability calls,
392 selector-comparison calls = **1,064 calls / 36,176,000 tokens / $53.02976** at
the V4 rates. One candidate reserves 538 calls. Do not consume protected reserves
for discovery. Historical campaigns keep their original caps/rates; do not
retroactively price them under the new model.

## 6. What actually ran

The final detailed source of truth is `docs/learning-results.md` plus the exports.
All failed and no-change records were retained; no successful repair was inserted.

| Run | Saved ID / result | Key evidence |
|---|---|---|
| Initial GPT-OSS attempt | `campaign-f242a908b0974f7bb5b0aaada532a5fd`, STOPPED | 9 calls; early infrastructure errors and an interrupted episode; old errors lacked enough safe diagnostics to reconstruct every cause |
| Corrected GPT-OSS attempt | `campaign-32a99aae95b84c9a882bdae5083a6ed2`, NO_CHANGE | 28 calls; six EMPTY_FINAL_RESPONSE episodes, one completed workflow, one C5 violation; no fully triggered source qualified |
| Llama healthy | `campaign-6caceef34f12452faf17c20ad4cb649c`, COMPLETED | All eight checks passed; 5 model calls, 4 HTTP attempts |
| Llama repeated baseline (T039) | `campaign-63933675566f49a994eb3e5bb6145434`, COMPLETED | 36/36 trials; 30/30 scheduled fault trials triggered; zero infrastructure errors; actual Weave fixed-score evaluation verified |
| Llama learning | `campaign-c37774fdddf349308c8c08acb3517be6`, NO_CHANGE | 64 calls; 8 discoveries, no qualifying full-recipe violation; some invalid Explorer output used explicitly labeled fallback |
| DeepSeek V3.1 healthy | `campaign-6e8e5acf800343398e9e2af9ad869091`, COMPLETED | All checks passed; 5 model calls, 4 HTTP attempts, 5.807 episode seconds |
| V3.1 first learning | `campaign-86d3e2025fbd468398c0c47e03e3bc82`, STOPPED before fixes | 167 calls; 3/3 failure reproduction and reduction; corrupted Mechanic evidence IDs blocked diagnosis; 25 completed episodes plus one interrupted |
| V3.1 corrected learning | `campaign-e6ac7b05ebc049f6804d34dc04d4ef72`, NO_CHANGE | 829 calls, 119 completed episodes, no provider errors, 119 verified traces; four controlled diagnoses all inconclusive |
| V4 healthy | `campaign-8d21197c49074271a4e789f88e273718`, COMPLETED | All checks passed; 3 calls, 2 HTTP attempts, 8,067 input/186 output tokens, 3.645 seconds |
| V4 first learning | `campaign-47411e4541ec441aa26baaddf66d5a88`, NO_CHANGE | 56 calls; 1 completed order/7 safe unresolved; no provider errors; all 8 traces verified |
| V4 first evidence-handoff correction | `campaign-859d61a084ee4c15817219eeab197124`, NO_CHANGE | 49 calls; 3 completed/5 safe unresolved; no provider errors; all 8 traces verified, seven through later saved-evidence sync |
| **Final V4 learning** | **`campaign-40c46ebee7b247c49d4a0204dead1939`, NO_CHANGE** | **44 calls, 5 completed/2 safe unresolved/1 correct rejection; no provider errors; all 8 traces verified; only 3 whole fault recipes triggered** |

Latest campaign recorded configuration:
`179e48231ce4194f47997852ad7f5ecd2601e474790bc0c70391b29d5e8782f2`.
The preceding V4 evidence-handoff campaign has the same recorded configuration
hash: the final orchestration adjustment in `learning.py` was not one of the
changed hashed agent prompt files. These are separate campaigns; do not describe
the hash as a complete checkout fingerprint or merge their trials. Inspect
`lab/configuration.py` for exactly what each stored digest covers.

Earlier V4 healthy/first-learning configuration:
`0e84be88a9904d06000bb6e2731410fa95b117832fab46e46bb41bda9325f5c0`.
Corrected V3.1 configuration:
`1ef3a9de1d32c4149db83246fe1a02190dfa837327ab5bb7db482c0ffd0625c8`.

Useful verified remote references:

- [V4 connection smoke](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09bb0-f093-7152-b0c7-350facb29a2f).
- [V4 healthy order](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/9f61ce4d-410c-4a4e-b4e2-b8e856e398fc).
- [Final V4 completed fault episode](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/239e0e63-f280-463d-ba28-6b5b9973d2f7).
- [Final V4 correct rejection](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/dc7953e5-f35a-4055-bcf9-d6636f3a4ccd).
- [Llama baseline fixed-score evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09b7b-1890-78da-b9f9-1d7c162daf23).

Selected local artifacts to read, all relative to `artifacts/`:

- `v4-learning-final-20260913.json` and matching `.jsonl`: final export/CLI output.
- `v4-healthy-final-20260913.json`.
- `v4-learning-attempt1-20260913.json`, `v4-learning-attempt2-20260913.json`.
- `deepseek-learning-attempt1-20260913.json`, `deepseek-learning-final-20260913.json`.
- `llama-learning-final-20260913.json`, `llama-baseline-study-final-20260913.json`.
- `live-attempt-1-evidence.json`, `live-end-to-end-final.json`: older GPT-OSS history.
- `model-readiness-v4-direct-20260913.json`, `v4-direct-diagnosis-readiness-20260913.json`:
  successful isolated request/schema probes, not live policy acceptance.
- `v4-diagnosis-readiness-20260913.json`: default-thinking failure; empty final,
  `finish_reason=length`, 4,000 output tokens, about 30 seconds.
- `wandb-available-models-20260913.json`: actual account model-list snapshot.
- `final-v4-verification-20260913.log`: latest full test/build log.

Some smoke files end in `.json` but contain human-readable command output. Inspect
the file before assuming it can be parsed as JSON. `live_status.py` is an ignored
read-only local helper, not a guaranteed installed product command.

## 7. Errors, fixes and lessons already established

### Provider and request failures

- GPT-OSS sometimes returned no usable final content. Some older campaign errors
  were `finish_reason=stop` with short usage, so output-cap exhaustion was not
  proven for those failures. Do not flatten all historical failures into one cause.
- V4's separate default-thinking probe did exhaust 4K output with no final answer.
  W&B's documented thinking-off setting produced nonempty role responses quickly.
  Actor/action, report, Explorer and diagnosis probes passed. Current live V4 calls
  did not have empty final responses. Never use reasoning text as the actor report.
- Exact action schemas, JSON mode, temperature zero, and bounded schema-validation
  feedback were supplied. Original raw answers are retained. Format feedback
  consumes the existing turn allowance; invalid actions are not dispatched as HTTP.
- Runtime errors retain safe class/status/finish reason/actual usage without raw
  SDK exceptions, authorization headers, secret-bearing objects or model reasoning.
  There are no hidden SDK generation retries.

### Token admission and budget correctness

- UTF-8 byte admission rejected legitimate prompts; use the pinned offline model
  tokenizers. GPT-OSS, Llama 3.3, V3.1 and V4 are mapped explicitly. Unknown models
  use the conservative fallback; no runtime tokenizer download is allowed.
- Required Mechanic input measured 8,772 DeepSeek tokens, above the original 8K.
  Input admission became 32K and all current per-call reservations became 34K.
  Campaign schemas/defaults, protected tokens, pricing, freeze and tests changed
  together. Historical ledger caps remain authoritative for old runs.
- Tokenizer provenance/licenses are under `contracts/tokenizer/`. V4 tokenizer
  SHA-256: `8f9f37ca37fdc4f5fd36d5cf4d3b0e8392edb4e894fd10cc0d70b4957c8633cf`.
  V4 and V3.1 ordinary-content tokenization matched when special added-token
  recognition was disabled, but they retain separate verified assets/provenance.

### Explorer and Mechanic handoffs

- Explorer initially lacked exact primitive parameter schemas and usable trigger
  feedback. Those omissions were fixed; invalid selections remain recorded with
  explicit fallback attribution. Occurrence counts tool/service HTTP attempts,
  not total workflow steps. Pending upgrades can prevent confirmation faults.
- Explorer repeatedly sought safe unresolved results or unreachable combinations.
  It now gets neutral C1–C8 definitions, the public actor/runtime contract, its own
  chosen recipes/coverage, and verified ordered observations/reports/checks from
  prior completed discoveries. Completed untriggered attempts also inform the next
  selection; they still cannot qualify as repair proof. LAB_ERROR/incomplete
  episodes, other campaigns, reference B1 and sealed studies do not enter this
  optimization context. No known-good recipe is supplied as the model's answer.
- Mechanic once copied long evidence lists and corrupted opaque IDs. It now cites
  1–3 relevant exact observations and receives reference/schema correction within
  its existing two-call format allowance. Requests include actual control/treatment
  recipes, public execution limits, full reduction outcome summaries and prior
  source-validation candidate failures. No missing policy is manufactured.
- Challenger now receives actual already-tested fault recipes as well as hashes,
  so novelty decisions have usable context; existing challenge gates remain intact.

### Why the 119-episode V3.1 run did not propose a policy

This was investigated in code and saved data; it was **not a dropped handoff**.
The four interventions really completed three pairs each. Counts of target-check
failures in control/treatment were **3/1, 3/1, 2/1 and 2/0**. The unchanged support
rule requires **3/3 control failures and 0/3 treatment failures**. All diagnoses
were correctly INCONCLUSIVE; all eight discovery slots then exhausted.

The recurring failing V3.1 episode had **no final report after eight actor turns**,
not a secretly successful report. Some Mechanic narratives inaccurately described
a PENDING report even though the actual report was null. Keep the actual record
above the model's explanation. Earlier reduction results did not guarantee that a
fresh intervention control would fail 3/3; stochastic variation remains real.

### Weave and UI issues already fixed

- SDK log-level handling and canonical project case were corrected.
- Actual installed Weave evaluation summary envelopes are handled and tested.
- Bulk readback returned duplicate rows. Verification now retrieves the exact
  registered IDs and checks identity, hierarchy, completeness and equality with
  local public observations/reports. Existing matching calls can be reused without
  rerunning business actions. Flush alone is not verified evidence.
- Frontend ingestion projections were being validated as full backend objects,
  producing a malformed-response banner despite valid traces. The projection
  contract is corrected and actual verified links render in the browser.
- CLI waiting no longer mistakes transient rejection for finished learning; it
  also waits for scheduler finalization. Live backend automatic reload is disabled.

## 8. Code map: where to continue

Paths below start at the application root. Within a table cell, subsequent filenames share the nearest explicitly named directory unless another directory is written.

| Concern | Main files |
|---|---|
| Startup/settings/routes | `backend/app/main.py`, `config.py`, `lab/api.py`, `lab/coordinator.py` |
| Learning orchestration | `backend/app/lab/learning.py` — selection through persistence; begin here for missing stages |
| Episode execution | `backend/app/lab/runner.py`, `adapters/prototype.py`, `adapters/business_tools.py`, `adapters/journal.py` |
| Model roles/prompts | `backend/app/agents/actor.py`, `explorer.py`, `mechanic.py`, `agents/prompts/*.md` |
| Inference | `backend/app/providers/runtime.py`, `providers/wandb_inference.py`; shared model-specific options and frozen settings |
| Exact contracts/admission | `backend/app/contracts/models.py`, `contracts/tokens.py`, root `contracts/*.schema.json`, `contracts/manifest.json` |
| Budget/reservations | `backend/app/lab/budgets.py`, `lab/configuration.py`, `referee/freeze.py`, `cli/freeze.py` |
| Mock services/worlds | `backend/app/simulator/business.py`, `faults.py`, `storage.py`, `control.py`, `clock.py` |
| Fixed checker and reduction | `backend/app/referee/checks.py`, `reducer.py`, `diagnostics.py` |
| Reproduction/diagnosis | `backend/app/lab/reproduction.py`, `diagnosis.py` |
| Candidate execution/gates | `backend/app/lab/policy_interpreter.py`, `policy_state.py`, `policies.py`, `evaluation.py`, `challenge.py`, `promotion.py` |
| Local and remote evidence | `backend/app/lab/storage.py`, `evidence.py`, `tracing.py`; `telemetry/weave_reader.py`, `worker.py`, `outbox.py`, `evaluations.py`, `datasets.py` |
| Aria | `backend/app/telemetry/aria_bridge.py`, `lab/aria_evidence.py`; deferred, no invented API |
| Regression/external studies | `backend/app/lab/regressions.py`, `regression_executions.py`, `portability.py`, `search_benchmark.py`, `audit.py`; `integrations/registry.py`, `external_agent.py`, `regression_runner.py` |
| Browser API/UI | `frontend/src/api.ts`, `experiments.ts`, `components/RunControls.tsx`, `EvidenceScreen.tsx`, `SponsorEvidence.tsx`, `Timeline.tsx`, `PolicyPanel.tsx`, `CounterexamplePanel.tsx`, `DiagnosticPanel.tsx`, `ChallengePanel.tsx`, `RegressionControls.tsx` |
| CLI commands | `backend/app/cli/client.py`, `cli/freeze.py`, `scripts/*.sh` |

For nuanced boundaries, read the corresponding tests rather than inferring from
UI labels. Especially useful: `backend/tests/lab/test_counterexample_loop.py`,
`test_diagnosis_context.py`, `test_challenge.py`, `test_budgets.py`,
`backend/tests/providers/test_runtime.py`, `backend/tests/test_providers.py`,
`backend/tests/contracts/test_token_admission.py`, `backend/tests/agents/`,
`backend/tests/telemetry/`, and `backend/tests/integration/`.

SQLite `records` columns are **`kind,id,payload,immutable`**; domain properties are
inside JSON `payload`. Do not invent separate SQL columns. Explicit `ORDER BY rowid`
is useful for insertion order; never infer “latest” from an unsorted query.
Authoritative records include campaigns, episodes, trials, budgets, selections,
mechanic_outputs, diagnostics, policies, trace_registrations, evidence and
evidence_retries. Private snapshots/control records must not become model prompts.

## 9. Exact remaining work

Read the original task definitions; this table is a guide, not a replacement.

| Open task | What is missing and what unlocks it |
|---|---|
| **T065** | Real generated repair path: eligible repeated failure, retained/reduced source, supported diagnostic, original model policy, three source pairs, four challenges × three pairs, fixed promotion comparison and persistence/restart evidence. No accepted learned policy exists. This is the priority. |
| **T088** | Complete sponsor chain beyond already-verified Inference/Weave baseline evaluation: versioned generated regression dataset, reduced/challenged evidence, Finished campaign and automatic Aria analysis. Aria remains explicitly deferred; do not check the whole task because Inference works. |
| **T097** | Freeze an actual accepted policy and exact core configuration/manifests; external identity can remain separately pending. Do not substitute B0 or handwritten B1 for a missing learned arm. |
| **T100** | Fresh exported regression execution, independent-agent transfer, and equal-budget selector measurements. Existing adapter is Hugging Face smolagents `ToolCallingAgent` 1.26.0, revision `12c1bc820eca50ace6f80a21d90426d41d74f845`, Apache-2.0. Source review/offline conformance passed; measured live transfer did not run. Preserve native agent logic. |
| **T102** | One sealed final audit: eight cases × three trials × B0/B1/L = 72 episodes, with raw outcomes/denominators/overhead, after freeze. No tuning from audit results. |

**T039 is already checked**: six development cases × three B0/B1 pairs = 36 Llama
baseline episodes, with actual Weave evaluation readback. That is not a V4 baseline,
and the dashboard's single healthy baseline button is not the 36-trial study.

Suggested next approach, with no promise of finding a repair:

1. Verify the transferred working tree/evidence before doing experiments. Read the
   final V4 selections, ordered public results, and actual trigger coverage. Do not
   debug provider credentials as if the old empty-response issue were still current.
2. Identify the smallest real blocker to reaching T065: no repeatable eligible
   failure, inconclusive diagnosis, malformed proposal, failing candidate, or missing
   evidence. They require different responses. Current V4 lacks a qualifying failure;
   V3.1 found failures but its fresh controlled diagnostics were inconclusive.
3. If further live testing is requested, choose a bounded development experiment
   with a stated purpose and keep all outcomes. Prefer fixing a demonstrated missing
   context/contract problem over adding features. Do not rerun identical valid
   groups until lucky, hardcode a successful policy, weaken the actor/checker,
   or mine sealed/reference solutions to force a demo.
4. When a real candidate qualifies, let the existing paired source → challenge →
   promotion path execute and inspect each persisted object. If no source qualifies,
   say so plainly: ordinary live operation works, automatic repair is still unproven.
5. Update exact checkboxes and result docs; only then proceed to dependent studies.
   Finish with the user guide matching commands actually verified on the new host.

The fixed gate order is intentional. Reproduction requires three fresh same-check
failures. Reduction is a finite local search, not a universal minimum. Supported
diagnosis needs 3/3 failing controls and 0/3 target failures in treatments.
Candidate source validation needs all three valid pairs repaired with no candidate
check failures; challenge needs four meaningful repeated schedules. Promotion
uses separate fixed cases and strict gain/no-regression rules. Read implementation
and protocol before changing any of these; more credits are not evidence.

## 10. Starting, inspecting and testing on the new host

Do a continuity check first. Confirm actual roots, Git state, `.env` existence
without reading it into chat, and availability of the final campaign in SQLite.
No model calls are needed to read files, run offline tests, start services, or load
saved UI recordings.

From the application root, for a fresh compatible local environment:

```sh
./scripts/setup.sh
./scripts/test.sh
```

Setup installs pinned dependencies and preserves an existing `.env`. It does not
install Python 3.12 or system tools for you. Use the project-local `.venv`; copied
environment repair should preserve the old environment until replacement works.
Some machines need the browser runtime expected by Playwright; inspect the actual
test error and `frontend/tests/playwright.config.ts` before changing dependencies.

Run the three services in separate terminals (keep them open):

```sh
./scripts/start-simulator.sh       # localhost:8001
./scripts/start-live-backend.sh    # localhost:8000; startup makes no paid calls
./scripts/start-frontend.sh        # localhost:5173
```

Check for existing listeners first. Use the live launcher for the recorded V4
configuration, even if a backend was previously running. Restart deliberately
between changes; do not edit model/prompts/scorer/limits during a scored run.
If your own environment already exports model/rate values, the launcher's defaults
do not override them: inspect the safe status/campaign configuration.

Read final status without running a model:

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli.client status \
  --campaign campaign-40c46ebee7b247c49d4a0204dead1939
```

Useful local read endpoints: `GET /api/config/status`,
`GET /api/campaigns/ID`, `/api/campaigns/ID/configuration`,
`/api/campaigns/ID/experiments`, and `/api/episodes/ID`.
`backend/app/cli/client.py` exports `request(method,path,body=None)` for localhost.

In the UI, paste the final ID into **Open saved campaign → Load recording**.
Inspect Fault × policy ledger, Evidence timeline and Sponsor evidence. Saved
playback/readback does not start another run. **Exit playback** before creating a
new campaign. Look for backend connectivity and the expected model in the receipt.

Export saved evidence to a **new filename** without inference:

```sh
./scripts/export-evidence.sh --campaign CAMPAIGN_ID \
  --output artifacts/handoff-inspection.json
```

Explicit live commands, only when continuing the approved live work:

```sh
WANDB_PROJECT=Faultlab WANDB_MODEL='deepseek-ai/DeepSeek-V4-Pro-0813' \
  ./scripts/smoke-sponsors.sh --confirm-entity shreetbohara-quinstreet \
  --max-output-tokens 2000

./scripts/run-demo.sh --mode baseline --execute-live --wait
./scripts/run-demo.sh --mode learn --execute-live --wait
```

`baseline` is the CLI mode name for a healthy run; **`--mode healthy` is invalid**.
Do not run both a UI Start and a CLI demo for the same intended single campaign:
the CLI creates/starts its own campaign. A valid command exiting or a queued ID
does not prove a remote study has completed. Read saved terminal status/results.

If `WAITING_EVIDENCE` appears, **Retry evidence sync** (or POST
`/api/campaigns/ID/retry-evidence` with `{}`) retries saved evidence, not completed
business calls. It can resume an already-authorized paused learning loop and thus
future model calls. Use it for actual pending evidence, not to rerun an unfavorable
business trial. Stop through the UI or `app.cli.client stop --campaign ID` to
prevent new execution while preserving records. An in-flight effect may commit.

Last full test result: **356 backend tests, 20 frontend tests, production build,
three browser checks passed**. One opt-in actual-local offline execution test was
skipped; actual live UI/readback was verified separately. There was one upstream
Starlette/AnyIO deprecation warning. Do not claim the skipped test ran. A prior
offline-local browser test had passed on the original machine at an earlier
milestone; it is historical, not the last suite result.

## 11. MCP / Codex tools / accounts

The product's W&B integration uses the installed Python SDKs and HTTP API. It
does **not** require this Codex account's private MCP connection to function.
A normal shell/file tool is enough to inspect code, run tests and operate the CLI.
Browser automation is useful for UI verification, but tool names and persistent
browser/tab/session handles from the previous Codex conversation will not transfer.
Use the new agent's available browser tools; do not hardcode old session IDs.

The previous agent used terminal/file tools, browser UI automation, official web
documentation, and document rendering. No image generation is needed for this
handoff. Optional plugins should not block ordinary backend continuation.
Aria requires its actual documented account/UI automation, not an invented MCP or
REST endpoint. TypeSafe integration is waiting on sponsor protocol instructions;
do not guess its protocol or silently swap providers.

The Word guide was generated from `docs/user-guide.md` by the ignored
`artifacts/build_user_guide.py`, then rendered and visually inspected. That helper
contains the old absolute application root: adapt it if reused. The previous
Codex-bundled Python/document renderer path is host-specific; do not assume your
friend has it. Markdown is the simplest portable guide and handoff format.

## 12. Communication and completion standards

- Explain in simple terms what worked, what failed, and the next concrete step.
- Keep the user informed during long live experiments. Distinguish model/API
  failure from a valid truthful business outcome and from an unproven repair.
- Preserve `.env`, private controls, immutable raw proposals, failed trials and
  all earlier model/configuration identities. Never publish local secrets/evidence
  simply because the application repository is public.
- Update the checklist by actual evidence. A passing offline double does not clear
  T065/T088/T097/T100/T102. Do not change checkers to obtain the desired result.
- This handoff accompanies the source update the user requested for GitHub. Its
  preparation and publication do not start paid execution, deployment, Aria setup,
  policy acceptance or an external study. Read the receiving user's current request
  before taking those actions.

The most useful first response from the next agent is a short continuity report
and a justified next step, not another full architecture plan.
