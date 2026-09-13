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
