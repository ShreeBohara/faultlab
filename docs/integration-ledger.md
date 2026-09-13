# FaultLab acceptance and integration ledger

Current live status (2026-09-13): Llama baseline measurement completed all 36 trials. The subsequent DeepSeek V3.1 learning attempt completed 119 episodes with verified traces and no provider errors, but no qualified repair. The selected model is now DeepSeek V4 Pro 0813 with documented thinking disabled; healthy execution passed, and its final learning campaign completed 44 model calls without provider errors with all eight traces verified. No fixed check failed under V4. The 2026-09-13 V3.1 repair-loop campaign then reached a supported diagnosis, a generated policy, a passing source validation and a challenge counterexample before ending NO_CHANGE; promotion and an accepted policy remain unverified live. The dated entries below preserve earlier implementation and experiment milestones.

Implementation started 2026-09-12 under the explicit Step 2 request. Application checkout
was clean. Existing skeleton is preserved. The initial implementation request did not authorize live calls; the user separately authorized the live validation recorded below. All measurements below distinguish code/tests from experiments.

## Contract freeze: faultlab-seams/v1

Canonical Python schemas: `backend/app/contracts/models.py`; JSON exports: `contracts/`.
Strict model-facing actions, fault/policy grammar, report semantics, purposes/splits and
trial requirements follow the reviewed spec. Canonical content hash is SHA-256 of sorted
compact UTF-8 JSON, no nonfinite values. Dates serialize UTC via model_dump(mode='json').
Use model_validate_json for stored JSON (strict datetimes/tuples); never weaken model validation.
Policy hashing covers content only; no coordinator metadata. Healthy FaultSpec may have zero
primitives under trusted evaluator control; ExplorerOutput requires one or two.

Exclusive writers: LEAD contracts/config/dependencies/main/scripts/docs; WORLD simulator,
referee, audit and domain tests; LOOP lab/agents/adapters and tests; SPONSOR providers,
telemetry and tests; UI frontend/src and frontend/tests; PORTABILITY integrations and tests.
No worker changes shared schemas, dependencies or this ledger; requests go to LEAD.

Frozen seams (narrow internal support types may stay within their domain):

- WORLD exports `app.simulator.main:create_app` and `app`. Separate HTTP process on 127.0.0.1:8001.
  Controls use `X-FaultLab-Control` configured locally; business uses `X-FaultLab-World`,
  `X-FaultLab-Capability`, `X-FaultLab-Call`, `X-FaultLab-Attempt`. Controls create world from
  TaskIntent + FaultSpec + reviewed fixture, return world_id/capability. These values are private.
  Control client API and Referee invocation are finalized with LOOP before its broker integration.
- LOOP owns `LabStore(path)` and `get_record(kind,id) -> dict|None`,
  `put_record(kind,id,payload,*,immutable=False)`, `list_records(kind) -> list[dict]` for
  SPONSOR outbox persistence. Campaign/policy/event methods additionally use atomic transactions.
- SPONSOR `RuntimeProvider(settings, live_authorized=False, client_factory=None)`, async
  `complete(messages, *, role, max_output_tokens=2000, timeout_seconds=20)` returns content,
  model_id, input_tokens/output_tokens (nullable), cost_usd (nullable); `close()`.
  No auto model discovery or retries. Actual dispatch requires frozen campaign budget admission.
  Runtime tracing uses a separately bounded SDK worker. Reader receives exact authorized
  project/call IDs and local metadata, with authorization before reads/return. It never accepts
  arbitrary model queries. LOOP supplies registered metadata and store seam.
- LOOP exports `create_router(...)` from lab/api.py and an injectable service/coordinator;
  LEAD mounts it without network calls during import/startup. REST follows integration-api.md.
- WORLD reducer/intervention callbacks consume fresh TrialResult values; no saved-answer replay.
- PORTABILITY runner consumes RegressionBundle and trusted registry/profile; default validation
  and playback are zero-effect. Bundled executable code is never imported.

New application settings use FAULTLAB_ prefix. Defaults: offline, 18 HTTP attempts / 8 actor
calls / 4 waits / 20 ticks / 32 policy steps / 90 seconds; campaign ceilings 6000 calls,
60M tokens, $100 when priced. 1064 calls/10.64M tokens remain reserved before development.
Live Start requires configured enablement, confirmed entity and valid caps; configuration
alone is not a request. Page loads, health, imports, tests, validation and playback stay offline.

## Acceptance ledger at the implementation handoff

| Gate | Status | Evidence / remaining input |
|---|---|---|
| Existing foundation | Verified offline | Original 20-test baseline preserved; expanded suite below |
| Shared schemas | Verified offline | Strict models, canonical JSON schemas, generated TypeScript and export parity tests |
| Software implementation | Independent offline implementation complete | All application lanes and T105–T112 review fixes verified; six measured tasks remain open |
| Integrated offline verification | Passed | Final: 269 backend tests, 18 UI tests, TypeScript/Vite build; all four browser cases including actual local backend/simulator |
| Core learned improvement | Unmeasured | Requires actual generated candidate, fresh reproduction/reduction/intervention/challenge/promotion and audit benefit |
| Diagnostic witness | Verified scoped offline experiment | Actual 30 loopback HTTP probes plus available-status control; docs/diagnostic-evidence.json; excluded from gain/search |
| Live Weave + Aria | Explicit live run pending | Runtime/offline adapters verified; actual credited-model access, remote traces/evaluation/dataset and automatic Aria history/output unverified |
| External validation | Source and adapter verified offline | Pinned independently authored smolagents 1.26.0; trusted runner, native adapter and 36-trial fixture orchestration tested; real external model study unmeasured |
| Selector comparison | Implemented and verified offline | Eight selections × three trials per selector; actual model comparison unmeasured |
| Publication/deployment/submission | Not requested | Owner action remains separate |

No synthetic test result, manual policy, internal alternate actor, URL entry, or documentation
checkbox satisfies a live, generated-learning or independently sourced measurement gate.

## Shared foundation evidence

T001/T002: existing checkout clean; obsolete guidance replaced; original 20 tests/build passed.
T003/T004/T005/T008/T013: strict contracts and TypeScript declarations exported; nine focused
wire tests validate actor authority, report shape, IDs, policy bounds/hooks, purpose/split
mapping, schema parity, UTC time, challenge completeness and zero-effect replay modes.
Python dependency check reports no conflicts. Local test network guard permits only explicitly
marked loopback HTTP; all other tests retain outbound socket prohibition. Frontend unit and
browser test tooling installed locally with pinned dependency/lock records. No global installs.
T089: external source intake recorded smolagents 1.26.0 and immutable revision/license/file hashes;
compatibility and measured external study pending, never satisfied by the source-review record.

## First integrated slice

- 22 foundation/config/contract checks pass, including provider-free health with configuration
  loading forbidden, real simulator HTTP health, strict response inputs and local process bindings.
- Two real HTTP integration checks pass: an explicitly labeled offline B1 reference upgrades
  and confirms, persists its original report/verdict, reloads read-only history without effects,
  and leaves remote evidence local_recorded. Live Start with absent configuration rejects before
  any world/model dispatch. This is local plumbing evidence; B0/live trace acceptance is pending.
- Three API lifecycle checks pass: duplicate start is idempotent, concurrent campaign/reset
  conflicts, immediate stop with epoch invalidation, history retention, invalid inputs, and
  event pagination across private rows. The controlled blocking runner is an offline fixture.
- Sponsor preflight reports installed SDK compatibility and 0 provider calls; all 69 sponsor
  offline tests pass (1.64 seconds in lead recheck). Actual accounts/Aria remain unverified.

## Fixed diagnostic experiment

`backend/tests/integration/test_diagnostic_evidence.py` passed in 3.97 seconds using real
localhost HTTP: 30 probes, two evidence_gap_v1 worlds with distinct private effects and
matching normalized public transcripts, plus available_status_v1 control with a succeeded
receipt. Missing probes or a distinguishing control returns INCONCLUSIVE. The sanitized
result is docs/diagnostic-evidence.json. This verifies the scoped capability demonstration
(SC-011 fixture evidence), not an autonomous finding, repair, or main-contract measured gain.


## Verified handoffs and current closeout

Checked task IDs are reconciled in the specification `tasks.md`. Original measured tasks
T039, T065, T088, T097, T100 and T102 remain unchecked. A completed implementation/test
item does not imply its later live dependent measurement has run.

- UI handoff: T067, T069–T076, T078, T086 and T095 passed 18 Vitest tests, TypeScript/Vite
  production compilation and browser fixtures. The separate local integration browser run
  passed all four tests (actual offline B1 result, reload, report/matrix identity and no
  refresh-induced actions). Original proposal inspection is a read-only raw-record view.
- PORTABILITY handoff: T090–T092/T098 implemented. The latest combined runner/native-agent
  plus root integration run passed **65 tests in 12.53 seconds** after adding independent
  target service-hash validation. F3 reduction retains its original history-v1 fixture.
  Validation/playback make zero business/model calls; explicit fresh executions use new worlds.
- LEAD T027/T028/T077: scripts and router mounted; real HTTP offline prototype invocation,
  correlated readback with a labeled fake remote transport, outage/retry and context denial
  tested without changing original reports or rerunning business effects. Actual remote
  trace acceptance remains unmeasured. T080 actual local HTTP projection/40 stop requests
  measured p95 **0.583 ms** on the idle local coordinator; this is not a heavy-load result.
  Raw values are `docs/control-latency.json`.
- SPONSOR T061: versioned dataset publisher and offline lifecycle/privacy tests implemented;
  actual immutable remote dataset reference remains a connected acceptance gate.
- LEAD T094: trusted regression CLI validate/playback/export/execute, portability and selector
  wrappers documented and integration tested. Current `.env` contents were not overwritten.

Final convergence closes executable evidence compaction, required bundle fixture identity,
meaningful challenge novelty, trace retry/publication wiring, semantic response binding,
frozen configuration/cap admission, accepted-policy reuse and selector-only resource deltas.
The subsequent complete suite and final task reconciliation will be recorded below.

## Requirement coverage assessment

This table covers all 50 functional requirements. “Implemented/offline verified” identifies
software evidence, not measured completion of each dependent live acceptance scenario.

| Requirements | Implemented/offline verified evidence | Remaining measured gate |
|---|---|---|
| FR001–002, FR005–009, FR011–012, FR033, FR035 | Decorator, scoped broker, per-world SQLite, actual F1–F4 HTTP faults, C1–C8 and original reports; simulator/referee and fault_campaign tests; 18 fresh B1 worlds | Live decorated prototype/external measurements |
| FR010, FR013–014, FR037–042 | Runtime roles, bounded policy grammar, three-trial reproduction/reduction, interventions, four-schedule paired challenge and rejection feedback; lab/referee tests | Actual generated repair, reduction and measured gain |
| FR015–018, FR020–021, FR031, FR034, FR049 | Frozen configuration/manifests, paired evaluation, strict promotion, accepted-policy persistence, one active run, stop/restart and protected reserves; lab/world/integration tests | Genuine accepted policy, final audit and empirical B0/B1/L comparison |
| FR003–004, FR019, FR024–027, FR036 | Durable evidence/outbox, authorized exact-call reader, fixed-score/dataset publication, explicit W&B provider and supported Aria automation/capture; telemetry/provider tests | Real provider, Weave/evaluation/dataset and automatic Aria acceptance; integration readback uses a labeled remote double |
| FR022–023, FR048 | Persisted timeline, original proposal, policy/matrix, diagnosis/challenge and playback/fresh controls; UI and browser tests | Actual live findings to populate views |
| FR043–047 | Fixture-preserving data bundle, trusted runner, zero-effect validation/playback, explicit fresh execution, reviewed native smolagents adapter and study harnesses; integrations/lab tests | Six-case external transfer, accepted-bundle live rerun and selector measurement |
| FR028–030 | Scaffold extension, offline startup, fixed localhost bindings, secret exclusions, domain ownership and network-blocked default checks | Final complete verification below |
| FR032, FR050 | Setup/demo/runner/sponsor instructions, five exact handbook criteria, source/scaffold attribution, limitations and separate pending reports | Actual learned/sponsor artifacts and separately authorized publication/submission |

All 14 success criteria were assessed. SC002 and SC007 have offline fixed-check/control
verification. **SC011 is demonstrated as the required separate diagnostic fixture**:
30 real loopback probes, distinct private effects, equal declared public observations and
an available-status control; zero model calls and excluded from learned/search scores.
SC001 is partial because real correlated Weave retrieval is pending. SC003/SC009
(generated gain/reduction), SC006 (connected Weave/Aria), SC012 (independent transfer) and
SC013 (selector measurement) remain unmet. SC004/SC005/SC008/SC010/SC014 have software and
local demonstration support, but accepted-policy lineage, complete measured batches and
an actual learned end-to-end evidence story remain pending. No candidate means no empirical
challenge success; acceptance is not established by an empty set of promotions.

T063 verification: three actual SQLite/HTTP restart integration tests passed in 0.73 seconds.
An explicitly labeled acceptance-decision fixture survives process reconstruction; fresh
learn/compare reuse it, B0 stays empty, rejected/stale updates and incompatible settings
cannot replace it. Fresh worlds/conversations/operation identities are isolated. This
verifies persistence semantics; it does not establish a generated accepted policy.


LOOP implementation handoff: T010/T012/T018/T021–T024/T026/T033–T036/T042/T045,
T047–T060/T062/T064/T066/T068/T084/T085/T093/T099 have offline implementation/test
coverage. The latest domain run passed 46 tests in lab/adapters/agents. T058 orchestration
uses explicit model/evaluator doubles; actual simulator and original-report seams have
separate HTTP integration tests. T066's malformed/rejected/no-gain/flaky/inconclusive/
outage cases are covered across test_roles, test_evaluation, test_reproduction,
test_counterexample_loop, test_runner and test_challenge, rather than a duplicate collector
file. Their passing software checks do not complete measured T039/T065/T088/T097/T100/T102.


T038 final HTTP bridge check: two healthy/F1 post-commit timeout scenarios passed in
2.19 seconds using the production B0 actor with explicitly labeled scripted model responses,
actual loopback sockets and a remote trace double. F1 triggers after one real commit;
the same-request retry adds exactly one HTTP observation. The original report, complete
child-call inventory, outage/readback retry and single world/episode survive unchanged.
Combined with the 18-world B1 development run and fixed fault-order tests, this verifies
local B0/B1 orchestration without claiming measured baseline model behavior.


## Convergence verification

The independent semantic review covered 50 FRs, 14 SCs, 26 user-story acceptance scenarios,
10 architecture decisions and six constitution principles. Eight traceable remediation
tasks (T105–T112) were appended without replacing the original task definitions. Their
implementation is now complete; the final domain suite passed **59 tests in 1.05 seconds**.

| Task | Verified correction |
|---|---|
| T105 | Repeated public results use lossless references and field-specific ID aliases; representative 10-episode evidence dropped from 8,647 to 2,568 tokens without collapsing different error codes |
| T106 | Required signed fixture_id survives export/import/fresh execution, including history-v1 after removing F3 |
| T107 | Challenge novelty excludes seed-only changes and canonicalizes primitive ordering; four genuinely distinct feasible schedules remain required |
| T108 | Baseline exact-call readback, role/root hierarchy, versioned dataset wiring and immediate HTTP 202 durable evidence-only jobs; isolated services, 60-second deadline, restart interruption and per-ID outcomes; resolved trace outage can publish an eligible completed campaign once, with uncertain Aria outcomes retaining the reconciliation guard |
| T109 | Broker rejects mismatched transport, response shape, order, operation, service, intent and nested receipts before delivered evidence or policy use |
| T110 | Changed current model/source/service/interpreter or configured call/token/dollar caps reject before fresh execution; returned wrong model is a lab error; frozen audit initializes publication before all 72 planned actor episodes |
| T111 | Compatible accepted policy loads into fresh learn/compare after restart; explicit baseline stays empty and compare without learned policy rejects |
| T112 | Selector study/per-arm deltas include selection and actor usage, preserve unknown costs and exclude prior campaign spending; actual model and isolated study metadata attach to Explorer calls |

These corrections close software review findings. They do not establish the six outstanding
live/measurement task outcomes. Autonomous repair tests use explicitly labeled doubles;
actual HTTP integration checks separately verify the actor, simulator and original-report
boundaries. No W&B account, provider, Aria automation or external measured study ran.


## Final local delivery (2026-09-12)

`./scripts/test.sh` completed successfully: **269 backend tests in 24.65s**, **18 frontend
tests**, TypeScript/Vite production build (109 modules), and three browser fixture cases.
The default browser suite deliberately skips the actual-local case. With all three local
services running, `FAULTLAB_BROWSER_LOCAL=1 npm run test:browser` then passed **all four
browser cases in 6.4s**, including fresh world creation, original report/matrix identity,
reload and zero-effect recorded playback. The first closeout attempt found one stale UI
bundle fixture missing required fixture_id; it was corrected and the complete command
passed on rerun. Logs: `artifacts/final-offline-verification.log` and
`artifacts/final-local-browser.log`. Only upstream AnyIO and terminal-color warnings remain.
`pip check` reports no broken requirements; `git diff --check` passed.

The three local services remain available on 127.0.0.1 ports 5173 (UI), 8000 (API), 8001 (simulator).
The displayed recording is campaign-b61a6a40a9a442e991650ccbc41e1279, produced by the actual
`./scripts/run-demo.sh --mode baseline --wait` command: one completed deterministic-reference
episode, three HTTP attempts, zero model calls and all C1–C8 passed. Its matching sanitized
read-only export is `artifacts/verified-offline-evidence.json`. A screenshot from the
separate final browser scenario is `artifacts/verified-dashboard.png`. No refresh/playback/source inspection runs a provider.

Task reconciliation is **106/112 checked**. T039/T065/T088/T097/T100/T102 remain unchecked
for live baseline, genuine learning, connected sponsor evidence, actual learned-policy
freeze, external/selector measurements and final audit. All 50 FRs and 14 SCs have explicit
coverage/limitations above. Full measured specification acceptance is **not complete**.

The next bounded live action, if explicitly requested, is model listing for the actual
credited W&B entity followed by one `smoke-sponsors.sh` generation/Weave check (32 output
tokens, 20-second generation timeout, no SDK retry). Confirm current entity/project and
account access, then record exact model/prices/caps locally before any campaign. Model
selection was delegated; openai/gpt-oss-120b remains an unverified initial candidate.
No live call, W&B automation creation, publication, deployment or submission occurred.


## Usage walkthrough follow-up

The step-by-step guide review caught a missing operator entry point for T039: Run baseline
runs one healthy episode, while the required comparison needs six cases × three B0/B1
pairs. T113 adds `run-baseline-study.sh`, explicit scheduler admission, durable study/status,
36 predeclared fresh episodes, 144 B0-call reservation, unchanged empty policy, isolated
study context, protected later-study capacity and rejection of repeated same-campaign studies.
Stop, failed initialization and restart preserve outcomes without automatic reruns.

Seven domain tests passed through the real runner/ASGI simulator with clearly labeled model
and remote doubles; three CLI tests verify execution gating and read-only status. The full
backend suite then passed **279 tests in 35.57 seconds**, with the same upstream AnyIO warning.
Log: `artifacts/baseline-study-verification.log`. Actual paid baseline measurement T039 stays
unchecked. Current task count: **107/113 checked**, with the same six measured gates pending.
The frontend was unchanged, so the preceding 18-unit/4-browser/build evidence still applies.

`docs/FaultLab_Quick_Start_Guide.docx` is an editable three-page usage guide, rendered and
visually checked page by page. Its repository text source is `docs/user-guide.md`; the exact
remaining-study commands are in `docs/live-validation.md`. The README links both.

Readiness check (no provider calls): local W&B key present; entity shreetbohara-quinstreet,
project faultlab; model unset, live execution disabled, confirmed entity unset and prices
unverified. Installed SDK offline preflight passes. Keys were neither displayed nor changed.
The existing dollar cap is per campaign; a multi-campaign live plan must also track total
spending against the user's overall budget. Aria account access and UI automation remain
unverified until actual connected setup/checks.

## Authorized live validation followup on 2026-09-12 Pacific

The user explicitly authorized model discovery, one bounded smoke, and then a full learning cycle up to $100 for the confirmed W&B project. This supersedes the implementation-only live restriction for this particular run. Aria was explicitly deferred. The existing root `.env` is preserved.

Actual model discovery and a 78-input/78-output-token GPT-OSS generation with completed Weave readback succeeded in canonical project `shreetbohara-quinstreet/Faultlab`. The exact trace, verified rates and earlier failed checks are in `docs/sponsor-results.md`. First live campaign `campaign-f242a908b0974f7bb5b0aaada532a5fd` was stopped for diagnosis and is retained in `artifacts/live-attempt-1-evidence.json`; it establishes no learned gain. T114/T115 record SDK/readiness fixes and the omitted neutral Explorer schema/safe provider diagnostic work exposed by these checks. The corrected frozen campaign finished NO_CHANGE; its exact results and verified completed root/tool traces are recorded in `docs/learning-results.md`.

The guide is now `docs/user-guide.md` and the editable `docs/FaultLab_Quick_Start_Guide.docx`, with step-by-step purpose and frontend/backend explanations. This followup does not mark any of the six original measured gates passed merely because credentials or one connection trace work.

Corrected campaign result: eight valid model-selected recipes, eight episodes (one successful order, one C5 violation and six EMPTY_FINAL_RESPONSE infrastructure failures). No fully triggered source qualified for repair. Both completed root/tool inventories were verified and persisted after switching from duplicate-producing bulk results to exact-ID retrieval. 28 model calls and 49,161 returned tokens; admitted inference ceiling $0.01624, actual bill unknown. The full local regression suite passed 307 backend tests, 18 UI tests, production build and three browser fixtures; targeted telemetry checks cover the final retrieval fix. All six original measured gates remain open; Aria is deferred. The four-page guide was rendered and every final page visually inspected.

Final handover verification: evidence retry `evidence-retry-16ab70b2c38b49a0bbc526880b8b2f93` completed with two VERIFIED episodes and six SKIPPED_INELIGIBLE episodes. Matching saved calls were reused; no inference or business rerun occurred. Final evidence export: `artifacts/live-end-to-end-final.json`. The final telemetry suite passed 68 tests; T116 is checked, for 110/116 tasks complete. Aria remains awaiting setup as requested.

## Live flow follow-up on 2026-09-13

The user prioritized a complete working flow and authorized trying available W&B models. Llama 3.3 70B completed the healthy order and the six-case baseline: 36 valid trials, zero infrastructure errors, all 30 scheduled fault recipes triggered and fixed scores verified in Weave. Two incorrect model reports remain measured failures. Its separate 64-call learning attempt ended `NO_CHANGE` without provider failures. See `docs/baseline-results.md`.

DeepSeek V3.1 campaign `campaign-e6ac7b05ebc049f6804d34dc04d4ef72` completed `NO_CHANGE` after 119 episodes and 829 model calls. All 119 episode traces were verified; no provider failures occurred. Reproduction, reduction and diagnostic interventions ran, but all four fixed diagnoses were inconclusive and no repair qualified. The conservative admitted inference ceiling was $17.3261, with actual billing unknown. All attempts remain saved in `artifacts/deepseek-learning-final-20260913.json` and the learning-results report.

The configured model is `deepseek-ai/DeepSeek-V4-Pro-0813`. W&B documents thinking as enabled by default and supports disabling it with `extra_body={"chat_template_kwargs":{"enable_thinking":false}}`. The default-thinking diagnosis probe returned no final answer after 4,000 output tokens (`artifacts/v4-diagnosis-readiness-20260913.json`). With thinking disabled, action, report and Explorer checks were schema-valid (`artifacts/model-readiness-v4-direct-20260913.json`), and diagnosis passed at the actual 2,000-output-token/20-second ceiling (`artifacts/v4-direct-diagnosis-readiness-20260913.json`). Those probes establish request compatibility. Subsequent healthy execution and the final V4 learning attempt completed with no provider errors; the latter ended NO_CHANGE with 44 model calls and eight verified traces. No fixed-check violation qualified for repair, so repair/challenge/promotion remain unverified live.

The runtime keeps JSON mode, temperature 0 and zero automatic retries. Current admission is 32,000 input plus 2,000 output tokens per request, 204 million campaign tokens, 6,000 calls and a $100 campaign cap. At [W&B's V4 prices](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/) of $1.31/$3.96 per million input/output tokens, each call reserves $0.04984 and the 1,064 protected calls reserve $53.02976. Official tokenizer provenance is stored locally; no runtime tokenizer download or credential change is required. Model-specific [thinking settings](https://docs.wandb.ai/inference/response-settings/reasoning), prompts, source and prices are frozen in each new campaign. Aria remains deferred.


Final 2026-09-13 verification: T118/T120/T121 software fixes verified, including complete own-development Explorer evidence and model-specific request options. Full suite: 356 backend tests, 20 frontend tests, build and three browser checks passed; actual live UI verified separately. Checklist: 116/121 checked. Final V4 campaign `campaign-40c46ebee7b247c49d4a0204dead1939` is NO_CHANGE, 44 model calls, eight completed episodes, no provider errors and eight verified traces. Five original measured gates remain open; Aria stays deferred. See `docs/learning-results.md` for outcomes and limits.

## Repair-loop campaign on 2026-09-13 (after the Codex handoff)

Diagnosis handoff correction T122 verified by 357 backend tests. Live V3.1 campaign `campaign-44085f54a24144b78252d8eea211ebb8` finished NO_CHANGE: 995 model calls, 143 episodes, 143 verified Weave traces, zero provider failures, admitted ceiling $20.7955 with billing unknown. New live milestones with saved evidence: one SUPPORTED controlled diagnosis (POLICY_GAP), three model-generated candidate policies, one 3/3 source validation pass, one executed challenge with a found counterexample and automatic Mechanic feedback. Not reached: a surviving challenge, promotion, accepted policy, freeze, regression dataset or restart evidence. Five original measured gates remain open; Aria stays deferred. See `docs/learning-results.md`.
