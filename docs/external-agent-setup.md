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

## Native adapter v2 (first build run live September 29, 2026; v2.1 labels not yet run live)

FaultLab now has two declared adapters for the same unmodified smolagents 1.26.0 `ToolCallingAgent`.
They are separate agents: each has its own entry point, prompt hash, adapter hash, registration,
plans and history, and their results must never be pooled.

* **Adapter v1** (`smolagents-toolcalling-v1`, agent kind `smolagents`): unchanged and still the default
  native choice. `backend/app/integrations/external_agent.py` is byte-identical to before v2, and a golden
  test (`backend/tests/integrations/test_native_adapter_v1_golden.py`) pins every byte v1 sends to the model.
* **Adapter v2** (`smolagents-toolcalling-v2`, agent kind `smolagents-v2`, shown as "smolagents
  ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)"). It runs the same agent,
  built by v1's own code, and adds only the two report fixes the reference Actor already received:
  1. **Short evidence labels, numbered over what the agent is shown** (adapter protocol
     `faultlab-native-adapter/v2.1-shown-order-labels`, since September 30). Every observation v2 hands to the
     agent shows its `evidence_id` as a short label `obs-N`, where N counts the observations in the order v2
     first showed them to the agent: `obs-1`, `obs-2`, ..., `obs-n`, with no gaps. An observation keeps its label on
     every later turn. Within one tool result, rows are numbered in the order the agent reads them (sorted keys,
     then list order). When the agent calls `final_answer`, the cited labels are decoded back to the real IDs
     before the report is validated. The decoding is exact, and it only decodes labels the agent had already been
     shown when it made that request. Any other token (for example `obs-99`, `OBS-1` or a label with a stray
     character) is kept as written and fails exactly as before. Nothing else in the report is changed.

     The journal can hold observations the agent is never shown. Two cases exist today: the status read of a
     `before_confirmation` policy step that does not block, and the first attempt of a write the broker retried
     inside one tool call (the tool result shows only the last attempt; this happens in dev-6 and other F1/F4
     fault cases). Such an observation gets **no label**. If it is shown later (for example in the full
     observation list after the business budget closes), it gets the next number then. So after a broker-retried
     send the agent sees `obs-1`, `obs-2`, `obs-3`, and `obs-3` decodes to the send's second attempt (journal
     row 4).

     *Why this changed.* The first v2 build numbered journal positions, so in that case the agent saw `obs-1`,
     `obs-2`, `obs-4`. A gap in the labels invites a guessed `obs-3`; v2.1 removes the gap from what the agent sees.
     In the first live v2 run (campaign `b05ac280`, September 29) the agent did **not** guess: all 53 reports cited
     only labels it had been shown. The failure there was the **Mechanic's**: reading reports whose cited rows skipped
     the hidden attempt (`o1`, `o2`, `o4`, `o5`, `o6`), it claimed a citation of an undelivered observation, proposed
     `CONTRACT_EVIDENCE_GAP`, and the diagnosis ended INCONCLUSIVE. **v2.1 does not change what the Mechanic reads**
     (see *What FaultLab's own models read* below), so it does not address that misdiagnosis; whether a Mechanic now reads such reports
     correctly is unmeasured.

     The `report_submitted` event records the cited tokens as written (`cited_evidence_tokens`), the decoded IDs,
     the label map as shown by that request (`evidence_labels`), `labels_shown_to_agent`, any
     `cited_tokens_not_decoded` (it replaces the first build's `cited_unshown_labels`, which no longer applies),
     the final-turn flag and the response contract.

     *What FaultLab's own models read.* The diagnosis and candidate Mechanic and the Explorer never see a label the
     adapter decoded: their evidence summaries show each report with its decoded IDs, written as that episode's
     `oN` row aliases (the Nth recorded observation), the same ID space as the observation rows they are shown.
     A token the adapter did **not** decode (a guess such as `obs-4`) is part of the saved report and reaches them
     as written, next to the aliases (it also fails C6).
     That numbering counts every recorded observation, including ones the agent never saw, so it can differ from
     the agent's `obs-N`, and a report that cites only what the agent saw still skips the hidden row (for example
     `o1`, `o2`, `o4`); that view did not change. The v2 contract text they receive (`actor_contract.memory` and the
     adapter protocol) now says exactly this. v1 and reference-Actor views are unchanged.
  2. **A strict final-report turn.** On the turn where FaultLab requires the report (the eighth turn, or
     sooner if business calls closed), v2 offers only `final_answer`, says it is the only allowed tool, and
     asks the provider for structured output of exactly `{"name": "final_answer", "arguments": {"answer":
     <TaskReport>}}` (new response contract `native_final_answer`). The size check for that request counts
     the structured-output schema too, and it runs before the turn is charged, as the reference Actor's does.
     So a final request that is too large is refused without being charged, like any over-limit turn in v1.
     An output that is still invalid is not repaired, and a business call on that turn is refused before it
     is sent, as in v1.

  The step count stays at v1's 8: the analysis found the meter's final turn already lines up with the eighth
  smolagents step, and v2 refuses to start if an episode's actor-call cap ever differs from 8.

Choose v2 explicitly: in the dashboard pick it under **Reviewed agent**, or register it with
`POST /api/agent-registrations {"agent": "smolagents-v2", ...}` or
`./scripts/run-regression.sh register --agent smolagents-v2`. Register again after every runtime change,
as for v1. **The v2.1 labels changed v2's adapter protocol, which is part of v2's prompt hash**, so v2 must be
registered again, and it is a different agent identity from the first v2 build: a discovery v3 agent history for
v2 does not include episodes run by the first v2 build (September 29), and their results must not be pooled. v1's
module and prompt hash are unchanged. `registry.py` is part of v1's adapter hash: adding v2 changed it (`61497db3…` →
`fa7a58db…`), and on September 30 the review fixes changed it again (`fa7a58db…` → `6f303264…`) so that a new v2
registration records the v2.1 label rule in its limitations (registrations are immutable). v1's history identity does
not include the adapter hash, so v1's history is unaffected, but **v1 must be registered again too** (as after every
runtime change); an idle campaign saved under the old runtime cannot be started (create a new campaign), but it stays
readable. Each `report_submitted` event of v2 records the cited tokens as
written, the decoded IDs, the label map, the labels shown to the agent, any tokens not decoded and whether the
report came from the strict final turn.

**Older checkouts.** A store that contains v2 plans needs this runtime or a later one. A checkout from before
v2 does not know the `smolagents-v2` agent kind: it reports those valid plans as "missing, corrupt or
inconsistent" and blocks them, but it does not change them. Open such a store with a current checkout.

Nothing in the gates changed: no referee, simulator, C1-C8 contract, promotion, challenge or evaluation code,
and no threshold. Evidence (identity values, golden capture, mutation checks, test log): `artifacts/product-native-v2-2026-09-29/builder/`.
