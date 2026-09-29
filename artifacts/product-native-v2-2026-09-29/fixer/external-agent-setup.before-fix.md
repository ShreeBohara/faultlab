# Independently authored agent intake

Selected candidate: Hugging Face smolagents `ToolCallingAgent`, version 1.26.0,
revision `12c1bc820eca50ace6f80a21d90426d41d74f845`.
Source: https://github.com/huggingface/smolagents/tree/12c1bc820eca50ace6f80a21d90426d41d74f845
The upstream Apache-2.0 license and source digests are recorded in
`external-agent-source.json`. Source was fetched for read-only review into ignored
`artifacts/source-review/smolagents/`; it was not executed by source intake.

This is an independently authored general tool-calling agent implementation from Hugging
Face, not a FaultLab-written second actor. Its native reasoning loop and prompt template
must remain intact. FaultLab supplies the synthetic task and transparent reviewed public
tool adapters; it may not insert an optimal order workflow and credit that to the source.
Apache-2.0 attribution/license preservation applies to any redistributed upstream files.
No one was contacted, and no third-party credentials or real business environment is used.

Compatibility status: transparent native adapter and offline conformance verified. The selected tool-calling
class uses a native model→tools→observation loop, a final_answer tool, resettable memory,
and configurable max_steps/max_tool_threads. The code-executing CodeAgent is outside this
registration. Use max_tool_threads=1; all requests must still enter the same serialized
FaultLab broker and retain request identity. Generated tool arguments cannot select URLs,
files, private controls, new identities or a different oracle.

Required mapping: get_order/update_order/get_operation_status/send_confirmation map to
exact canonical business calls; final_answer must contain the original exact TaskReport.
Before/after hooks must wrap the same logical tool/report boundaries as the reference
adapter. No renderer may fill missing outcomes or replace the external agent on failure.
Each trial constructs fresh agent memory and a new synthetic world; C1-C8 use the same
private simulator oracle. Any hidden final-answer retry must debit the eight physical-call
limit; exhausted invalid output is a violation, not a synthesized report.

Target model access/pricing and live execution remain PENDING. The user delegated model
selection; `openai/gpt-oss-120b` is the initial unverified candidate. Freeze source,
adapter, native prompt, interpreter, target configuration and
six-case manifest before any B0/L pair. Both target arms use exactly the same target model,
prompt and limits; only the accepted transferred policy differs. Source model/prompt hashes
are historical provenance, not an equality requirement for a different target agent.

Implemented integration effort: a bounded local tool/model bridge and native-loop contract
suite, preserving upstream task memory and final-answer handling. No elapsed-effort metric
was recorded. The current combined integrations and local integration suite passed 65 tests,
including native fake-provider execution, response/policy conformance, safe bundle validation,
fixture preservation and repeated-study orchestration. These tests do not pass SC-012:
six cases × three fresh external B0/L pairs and fresh regression-bundle execution remain
unmeasured. An internal smoke registration is reported separately and cannot clear that gate.

## Native adapter v2 (September 29, 2026; built offline, not yet run live)

FaultLab now has two declared adapters for the same unmodified smolagents 1.26.0 `ToolCallingAgent`.
They are separate agents: each has its own entry point, prompt hash, adapter hash, registration,
plans and history, and their results must never be pooled.

* **Adapter v1** (`smolagents-toolcalling-v1`, agent kind `smolagents`): unchanged and still the default
  native choice. `backend/app/integrations/external_agent.py` is byte-identical to before v2, and a golden
  test (`backend/tests/integrations/test_native_adapter_v1_golden.py`) pins every byte v1 sends to the model.
* **Adapter v2** (`smolagents-toolcalling-v2`, agent kind `smolagents-v2`, shown as "smolagents
  ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)"). It runs the same agent,
  built by v1's own code, and adds only the two report fixes the reference Actor already received:
  1. **Short evidence labels.** Every observation v2 hands to the agent shows its `evidence_id` as its
     position in the episode journal (`obs-1`, `obs-2`, ...). When the agent calls `final_answer`, the cited
     labels are decoded back to the real IDs before the report is validated. The decoding is exact: a token
     that is not a label of an observation delivered by then (for example `obs-99`, `OBS-1` or a label with
     a stray character) is kept as written and fails exactly as before. Nothing else in the report is changed.
  2. **A strict final-report turn.** On the turn where FaultLab requires the report (the eighth turn, or
     sooner if business calls closed), v2 offers only `final_answer`, says it is the only allowed tool, and
     asks the provider for structured output of exactly `{"name": "final_answer", "arguments": {"answer":
     <TaskReport>}}` (new response contract `native_final_answer`). An output that is still invalid is not
     repaired, and a business call on that turn is refused before it is sent, as in v1.

  The step count stays at v1's 8: the analysis found the meter's final turn already lines up with the eighth
  smolagents step, and v2 refuses to start if an episode's actor-call cap ever differs from 8.

Choose v2 explicitly: in the dashboard pick it under **Reviewed agent**, or register it with
`POST /api/agent-registrations {"agent": "smolagents-v2", ...}` or
`./scripts/run-regression.sh register --agent smolagents-v2`. Register again after every runtime change,
as for v1. Each `report_submitted` event of v2 records the cited tokens as written, the decoded IDs, the
label map and whether the report came from the strict final turn.

Nothing in the gates changed: no referee, simulator, C1-C8 contract, promotion, challenge or evaluation code,
and no threshold. Evidence (identity values, golden capture, mutation checks, test log): `artifacts/product-native-v2-2026-09-29/builder/`.
