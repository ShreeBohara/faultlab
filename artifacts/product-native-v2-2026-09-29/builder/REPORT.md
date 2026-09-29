_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

# Native adapter v2: builder report (September 29, 2026)

I did not write REPORT.md. The harness refuses report files from this subagent, and I did not work around that. This whole text is the report; please save it as artifacts/product-native-v2-2026-09-29/builder/REPORT.md.

- **Cost:** $0. No provider, model, W&B, Weave or network call.
- **Not changed or opened:** no commit or git index change. I never opened .env, backend/app/referee/checks.py (only hashed through the product's own functions), heldout2, promotion.json or final-audit files. I never touched /Users/shree/FaultLab_Runs.
- **Status:** built and tested offline only. Not run live.

## 1. What was built

There are now two declared adapters for the same unmodified smolagents 1.26.0 ToolCallingAgent.

**Adapter v1** (entry point `smolagents-toolcalling-v1`, agent kind `smolagents`)
- Unchanged, and still the default wherever a default exists.
- `backend/app/integrations/external_agent.py` is byte-identical to before (sha256 `6c0909bf…`, pinned by a test).
- A new golden test pins every byte v1 sends to the model, plus v1's native_prompt_hash (`22515428…`, unchanged). I captured the golden from the unchanged code before writing any v2 code.

**Adapter v2** (entry point `smolagents-toolcalling-v2`, agent kind `smolagents-v2`)
- Shown as "smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)".
- Runs the same agent, built by v1's own `_native_agent` code: same template, memory, tools, max_steps=8 and planning off.
- It adds only the two fixes the reference Actor already had:

1. **Short evidence labels.** Every observation v2 hands to the agent shows its evidence_id as its position in the episode journal (obs-1, obs-2, …). This covers:
   - business tool results;
   - policy observations;
   - a blocked confirmation;
   - a blocked report;
   - the list shown after the business budget closes.

   The labels come from `app.agents.progress.evidence_labels`, the same way the reference Actor gets them. At final_answer, the cited evidence_ids are decoded with `decode_citations` before TaskReport validation:
   - The decode uses only the observations delivered by that request.
   - It is exact and total: obs-99, OBS-1, obs-01, "obs-1极", numbers and lists are kept as written, so they fail exactly as before.
   - No other part of the report is touched.

   The `report_submitted` event records the cited tokens as written, the decoded IDs, the label map, the labels actually shown, whether the report came from the final turn, and the response contract used.

2. **Strict final-report turn.** When `meter.final_turn` is true (the 8th request, or sooner once business calls close):
   - The request lists only final_answer. Its entry says "final_answer is the only allowed tool on this final turn."
   - The provider is asked for structured output via a NEW response contract, `native_final_answer`. Its schema is exactly `{"name":"final_answer","arguments":{"answer":<TaskReport>}}`.
   - Parsing stays native. An invalid output is not repaired.
   - A business call on that turn is still refused before dispatch, by v1's own check.

**Separation.** v1 and v2 are separate everywhere: registration, configuration, plans, history and bundle targets. Nothing treats v2 as the reference agent.

**Nothing in the gates changed:** no referee, simulator, C1-C8 contract, promotion, challenge or evaluation code, assess_pairs, thresholds, reference Actor or prompts/actor.md.

## 2. Step alignment (task item 4)

The analyst's finding shows no mismatch, so v2 keeps v1's 8 steps:
- Each smolagents step makes exactly one model request.
- A transport retry happens inside that request and uses no turn.
- The meter's final turn falls on the 8th request.
- smolagents' fallback (`provide_final_answer`) would be a 9th request, and `meter.model_call` refuses it before any provider request.

**Added guard:** v2 refuses to start, before any request, if an episode's actor-call cap is not 8. The registry already requires 8, so nothing changes today. The guard just makes "the final turn is always a regular step" true by construction.

**Tested:** a v2 episode that never answers sends exactly 8 requests and flags only the 8th. That request offers only final_answer, with the contract. The business call on it is refused (7 HTTP attempts, 7 logical calls), and the 9th request never reaches the provider. A report given on the 8th turn is accepted.

## 3. What the agent now sees

Fake counter IDs from the scripted offline episodes. Full capture is in `builder/before_after_examples.json`.

**One tool result (after get_order):**
- v1: `Observation: {"final_report_required":false,"observation":{"call_id":"call-…08","delivered_tick":1,…,"evidence_id":"evidence-0000000000000000000000000000000a",…,"tool":"get_order","transport":"ok"},…},"policy_observations":[]}`
- v2: identical bytes, except `"evidence_id":"obs-1"`.
- On ordinary turns, every v2 request equals v1's request with each real ID replaced by its label. This is tested byte for byte against the golden.

**Final-turn request (8th request of a polling episode):**
- v1:
  - message: `{"final_report_required":true,"remaining_actor_calls":1,"tools":[get_order, update_order, get_operation_status, send_confirmation, final_answer],"transport":"Return exactly one JSON object … No markdown. …"}`
  - provider arguments: `{max_output_tokens:2000, role:actor, timeout_seconds:20}`
- v2:
  - message: `{"final_report_required":true,"remaining_actor_calls":1,"tools":[{"name":"final_answer","description":"final_answer is the only allowed tool on this final turn. Finish with the original exact five-field TaskReport in the task contract.","inputs":{"answer":{…}}}],"transport":<the same v1 text>}`
  - provider arguments: `{max_output_tokens:2000, response_contract:"native_final_answer", role:actor, timeout_seconds:20}`

## 4. Files changed

**New**
- `backend/app/integrations/external_agent_v2.py`:
  - `_BridgeV2` subclasses v1's `_Bridge`. It inherits the transport retry, accounting, stop handling, provider-failure recording, model-identity check and business dispatch.
  - It overrides `generate` (final-turn flag, snapshot of delivered observations, reduced tool list on the final turn) and `dispatch` (labels, and its own final_answer handler).
  - `_FinalTurnProvider` adds the response contract on final-turn requests only.
  - `SmolagentsActorV2` and `adapter_protocol()`.
- Tests:
  - `backend/tests/integrations/test_native_adapter_v1_golden.py` (4) plus the fixture `backend/tests/fixtures/native_v1_golden_requests.json`
  - `backend/tests/integrations/test_native_adapter_v2.py` (31)
  - `backend/tests/providers/test_native_final_answer_contract.py` (7)
  - `backend/tests/lab/test_native_adapter_v2_product.py` (13)
  - `backend/tests/integration/test_native_adapter_v2_api.py` (5)
  - `frontend/tests/native-adapter-v2.test.tsx` (5)

**Changed**
- `backend/app/providers/runtime.py`:
  - New `native_final_answer` contract, built from `NativeFinalAnswer` wrapping TaskReport, plus `native_final_answer_protocol()`.
  - JSON-mode, actor_final_report and `actor_response_protocol()` keep their pre-change hashes (`376bde79…`, `0576de04…`, `4e6455ac…`), pinned by a test.
- `backend/app/integrations/registry.py`:
  - New entry-point constants and maps.
  - `adapter_hash(entrypoint)`: v1 still covers registry.py + external_agent.py; v2 also covers external_agent_v2.py and agents/progress.py.
  - `native_prompt_hash(entrypoint)`: v1 unchanged; v2 adds `adapter_protocol()`, which includes the final-turn text and the contract hashes.
  - freeze, register (v2 id prefix `smolagents-1.26.0-adapter-v2-`), verify, reviewed_actor, reviewed_actor_matches and current_registration_configuration all take the entry point, with v1 as the default.
- `backend/app/lab/run_plans.py`: new agent kind; v2 appears in run options with its label; discovery v1 and v3-history support it (v2 pre-check stays reference-only); plan binding goes through the registry maps.
- `backend/app/lab/runner.py`: native checks now cover both adapters.
- `backend/app/lab/operator_actions.py`: the API accepts `smolagents-v2`.
- `backend/app/cli/regressions.py`: `register --agent smolagents-v2`.
- `backend/app/lab/agent_history.py`: v2 gets the native identity shape. Its entry point and prompt hash keep its history apart from v1's. The rule text is unchanged, so saved v3 plans stay valid.
- `backend/app/lab/bundle_imports.py`: import targets name v2 as `smolagents-v2`.
- `backend/app/lab/diagnosis.py`: a v2 plan gets v2's contract and `adapter_protocol` for the Mechanic. The v1 branch is unchanged.
- Three existing tests adjusted, expected changes only: `test_agent_history.py` and `test_run_plan_api.py` (the new option), and `test_native_baseline_study_planned.py` (its lambda now accepts the entry point).
- **Frontend:**
  - `runPlans.ts`: AgentKind, AGENT_KINDS, isNativeAgent, agentName and NATIVE_V2_LABEL. Validators now accept 2 or 3 agents, with reference and v1 always present. They reject unknown kinds, and any pre-check protocol that claims a native agent.
  - `RunSetup.tsx`, `CampaignPlan.tsx`, `BundleImports.tsx`, `ImportedTrialEvidence.tsx`: show full adapter names.
- **Docs:** a section appended to `docs/external-agent-setup.md` (the native-agent integration doc), and one line in `docs/regression-runner.md`.

## 5. Identity values

Computed with the product's own functions (`builder/identity_snapshot.py`; before and after JSON saved).

**Unchanged:**
- simulator service `3ce5bcd2…`
- contract `6f9d7783…`
- interpreter `6da0714a…`
- scorer `19de811c…`
- capability `8e8e04af…`
- reference Actor prompt/source/adapter `12eabe7f…` / `99a9034f…` / `0cd810b7…`
- native source `2867b3fb…`
- v1 native prompt `2251542869cf…`

**Changed:**

| Value | Before | After |
|---|---|---|
| Runtime | `5583dcad…` | `7968b622443520f34a7549c09c2f0e628e8ce5e2b077972d18d23ecc3a3952b3` |
| Algorithm | `5c95f2a9…` | `934c9c642ef6ade969989856d12500c4ba3fa68c30847c7baac02cd089dc30ff` |
| v1 adapter hash (only because registry.py changed) | `61497db3…` | `fa7a58db41fc629294b3d379d600949ff41ceb7643c716894e06b677470dff21` |

**New:**
- v2 adapter `34878663f626e7b13d1f4ba71c96e6a55955aba360e5050fb484d2804be2ba0b`
- v2 prompt `19a2431270c12f4156f3ca49de730ac0f3400a289187a720e6d32b402ebccd9e`
- v2 adapter protocol `eda7dc84…`
- `native_final_answer` response format `e5ce062b…`

Every agent must be registered again under runtime `7968b622` before a live run.

## 6. Tests

**Full `scripts/test.sh`**, run once after the last code edit:
- backend: **2,816 passed, 180 skipped, 0 failed**
- frontend: **334 passed**
- build: passed
- browser: **17 passed, 1 opt-in skip**
- exit 0

New tests: 60 backend and 5 frontend. The previous baseline was 2,756 backend and 329 frontend. Log: `builder/full-test-sh.log`.

**Mutation checks** (`builder/mutation-checks.log`): 13 of 13 deliberate breakages were caught. Each file was restored byte-identically, sha256 checked. The breakages:
- labels removed
- decode removed
- decode against the live journal instead of the request
- no contract on the final turn
- all tools offered on the final turn
- step guard removed
- blocked-report observations not labelled
- validation error quoting decoded IDs
- v2 adapter hash omitting its module
- v2 history not native
- bundle target kind lost
- reference contract bytes changed
- v1 transport text changed (the golden test catches it)

The "decode against the live journal" breakage first survived, because in the native loop nothing can arrive between a request and its final_answer. I added a direct unit test for the rule, and it is now caught.

## 7. Choices and things not done

1. **v1's file is not touched, so two short pieces are restated in v2.** v1 writes its episode driver and its final_answer steps directly into its own bridge class. v2's copies are identical apart from the bridge class, the step guard and the decode. Parity tests run v1 and v2 side by side: one lost request, two lost requests, a wrong model and a cancellation. The whole retry and accounting loop is inherited, not copied.
2. **Where "the only allowed tool" is said.** The `transport` sentence is built by v1's shared code from v1's constant, so v2 says it in the final_answer entry of that same message, which is the only tool listed. The response contract is added by a thin provider wrapper, and ordinary turns reach the provider with exactly v1's arguments.
   - Input size: v1's code checks messages before charging the turn, and the provider checks messages plus schema before sending.
   - The largest 8-turn request is about 6,000 tokens (about 6,650 with the schema) against the 32,000-token limit.
3. **Validation errors quote what the agent wrote.** Decoding cannot change whether a report is valid. So when the decoded report fails, v2 shows the native pydantic error for the answer as written. Otherwise pydantic's quoted input would show fragments of real IDs (for example `['eviden…0000a']`).
4. **Labels are journal positions, as for the reference Actor.** In one case the native agent is shown fewer observations than the journal holds: a hidden first transport attempt of a retried business call. A guessed label for it would still decode. `labels_shown_to_agent` is recorded so this can be audited.
5. **`check_clock_drift_native.py` was deliberately not changed.** Its rule excuses only old v1's tick-0 bug, which v2 never had. Adding v2 there would only let a real v2 clock drift be excused. Tests show that a v2 episode passes the original `check_clock_drift.py`, and that a v2 report rewritten to tick 0 is not excused.
6. **Contract text kept identical.** v2 sends v1's TASK_CONTRACT and TRANSPORT_CONTRACT unchanged, so each fix is the only difference.
7. **Not done:** step-error events (the analyst's recommendation 4); `native_baseline.py` stays a v1 script; CURRENT_STATUS.md is left for the PM. Imported bundle reruns have no run plan, so there is no `episode_executions` record for either adapter; v2 is identified there by the registration and by v2's `report_submitted` fields.
8. **Not run live.** The effect of v2 on real failures is unmeasured.

## 8. Next live step (PM)

1. Register again under runtime `7968b622`.
2. Declare any v2 run as adapter v2 and never pool it with v1.
3. Measure the expected drop in no-report C5 failures (analyst buckets A and C/D). The dev-5 C3/H and dev-6 H failures should remain, as material for learning a policy.

## Returned fields

- backend: PASSED: 2,816 passed, 180 skipped, 0 failed (60 new tests; 3 existing tests updated for the expected new agent option / entry-point argument). Run once via scripts/test.sh after the last code edit, 1,047 s.
- frontend: PASSED: 334 unit tests (5 new in tests/native-adapter-v2.test.tsx); production build passed.
- browser: PASSED: 17 passed, 1 opt-in skip (scripts/test.sh browser stage).
- runtime: 7968b622443520f34a7549c09c2f0e628e8ce5e2b077972d18d23ecc3a3952b3
- files changed: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/integrations/external_agent_v2.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/integrations/registry.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/providers/runtime.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/run_plans.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/runner.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/operator_actions.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/diagnosis.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/agent_history.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/bundle_imports.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/cli/regressions.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/integrations/test_native_adapter_v1_golden.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/fixtures/native_v1_golden_requests.json, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/integrations/test_native_adapter_v2.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/providers/test_native_final_answer_contract.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/lab/test_native_adapter_v2_product.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/integration/test_native_adapter_v2_api.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/lab/test_agent_history.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/integration/test_run_plan_api.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/lab/test_native_baseline_study_planned.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/runPlans.ts, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/components/RunSetup.tsx, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/components/CampaignPlan.tsx, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/components/BundleImports.tsx, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/components/ImportedTrialEvidence.tsx, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/tests/native-adapter-v2.test.tsx, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/external-agent-setup.md, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/regression-runner.md, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/full-test-sh.log, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/identity-before.json, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/identity-after.json, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/identity_snapshot.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/golden-capture-provenance.txt, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/native_v1_golden_requests.captured-before-v2.json, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/mutation_checks.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/mutation-checks.log, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/test_before_after_examples.py, /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/builder/before_after_examples.json
