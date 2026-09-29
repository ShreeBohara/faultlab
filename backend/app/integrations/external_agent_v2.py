"""Declared native adapter v2 (entry point smolagents-toolcalling-v2) for the same unmodified smolagents agent.

v1 (app.integrations.external_agent, entry point smolagents-toolcalling-v1) is imported here and never
changed. v2 runs the same installed smolagents 1.26.0 ToolCallingAgent, built by v1's own code: the same
native prompt template, empty native memory per episode, the same five tools, max_steps=8, planning off,
one tool thread. It adds exactly the two report fixes the FaultLab reference Actor received, and nothing else:

1. Short evidence labels (the reference Actor's Phase 11 fix, faultlab-actor-context/v4-indexed-evidence).
   Every observation v2 hands to the agent -- a business tool result, the policy observations a hook added,
   a blocked confirmation, a blocked report, the observation list after the business budget closes -- shows
   its evidence_id as its 1-based position in the episode journal (obs-1, obs-2, ...), built with
   app.agents.progress.evidence_labels exactly as the reference Actor sees it; every other field is unchanged.
   At final_answer, the report's evidence_ids are decoded back with app.agents.progress.decode_citations
   BEFORE TaskReport validation. The decoder is exact and total, and it decodes only labels that v2 had
   already shown to the agent when the model request was made: every other token passes through unchanged,
   so it still fails exactly as before. The journal can hold observations the agent never sees -- the read
   of a non-blocking before_confirmation hook, or the first attempt of a write the broker retried inside
   one tool call (v1's tool result returns only the last one) -- and such an observation still has a
   journal position. Its label is never decoded, so guessing it cannot make a citation valid (the
   reference Actor's rule, app.agents.actor; that Actor is shown every journal row, so for it "shown" and
   "delivered" are the same). No other part of the report is touched; nothing is repaired.
2. A strict final-report turn (the reference Actor's reserved report turn). When EpisodeMeter.final_turn is
   true at a model request, the per-request transport message offers only final_answer, whose entry says
   it is the only allowed tool, and the provider is asked for structured output whose schema is exactly the
   native action {"name": "final_answer", "arguments": {"answer": <TaskReport>}} (response contract
   native_final_answer, app.providers.runtime). That request is admitted with the schema counted
   (validate_request_input, as the reference Actor does) BEFORE v1 charges the turn, so a final request
   that is over the input limit only because of the schema is refused uncharged, like an over-limit
   ordinary turn in v1, instead of being charged and then refused by the provider layer. Parsing stays
   native: v1's parser and smolagents' own error-to-next-step path handle any output, and an invalid
   output is not repaired. A business call on that turn stays refused before dispatch by v1's own check.

Shared with v1 as the same code (imported, not copied): the guarded smolagents import (no implicit .env
load), agent construction, the model wrapper and its single-action parser, request building, the bounded
transport retry, budget accounting, stop handling, provider-failure recording, the model-identity check and
every business-tool dispatch. v2 restates three short pieces because v1 inlines them with its own bridge:
the episode driver (SmolagentsActorV2._run, identical apart from the bridge class), the final_answer
handler (v1's steps plus the decode and the richer report_submitted record), and v1's request builder
(_request_messages), used only to admit a final request before it is charged; _FinalTurnProvider refuses
to send a final request that differs from the one admitted. Tests pin their parity.

Step alignment (analyst finding, artifacts/product-native-v2-2026-09-29/analysis): there is no mismatch to
fix. Every smolagents step makes exactly one model request (planning is off); a transport retry happens
inside that request and uses no turn; EpisodeMeter.final_turn is true at the 8th request (7 of 8 actor
calls used) or once business calls close. smolagents' own max-steps fallback (provide_final_answer) would
be a 9th request, and EpisodeMeter.model_call refuses it before any provider request. So v2 keeps v1's 8
steps and refuses to start if the episode's actor-call cap ever differs from them, so the meter's final
turn is always a regular model step and never smolagents' fallback.
"""
from __future__ import annotations

import asyncio
from copy import copy
import json
from types import SimpleNamespace

from pydantic import ValidationError

from app.agents.actor import ActorReportError
from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V4, EVIDENCE_LABEL_PREFIX, actor_context_protocol,
                                 decode_citations, evidence_labels)
from app.contracts.models import ReportAction, TaskReport, canonical_json, new_id
from app.integrations.external_agent import TASK_CONTRACT, TRANSPORT_CONTRACT, _Bridge, _native_agent
from app.integrations.registry import NATIVE_V1, NATIVE_V2, NATIVE_V2_DISPLAY_NAME
from app.lab.budgets import BudgetExhausted, StopRequested
from app.providers.runtime import (NATIVE_FINAL_ANSWER_CONTRACT, RuntimeProviderError,
                                   native_final_answer_protocol, validate_request_input)

ENTRYPOINT = NATIVE_V2
BASE_ENTRYPOINT = NATIVE_V1
PROTOCOL_VERSION = "faultlab-native-adapter/v2-shown-labels-final-turn"
DISPLAY_NAME = NATIVE_V2_DISPLAY_NAME
# v1's step count: external_agent._native_agent(max_steps=8) and SmolagentsActor._run(max_steps=8).
ALIGNED_STEPS = 8
FINAL_TURN_TOOL_DESCRIPTION = ("final_answer is the only allowed tool on this final turn. "
                               "Finish with the original exact five-field TaskReport in the task contract.")
LABELLED_FIELDS = ("observation", "policy_observations", "observations")


def adapter_protocol():
    """What v2 adds to v1, declared once; part of v2's prompt identity (registry.native_prompt_hash)."""
    reference = actor_context_protocol(ACTOR_CONTEXT_PROTOCOL_V4)
    final = native_final_answer_protocol()
    return {
        "version": PROTOCOL_VERSION, "base_entrypoint": BASE_ENTRYPOINT,
        "evidence_labels": {
            "reference_protocol": ACTOR_CONTEXT_PROTOCOL_V4,
            "evidence_naming": reference["evidence_naming"],
            "evidence_label_prefix": EVIDENCE_LABEL_PREFIX,
            "citation_decode": reference["citation_decode"],
            "labelled_tool_result_fields": list(LABELLED_FIELDS),
            "also_labelled": "observations of a blocked report; a report validation error quotes the answer as written",
            "decode_point": "final_answer, before TaskReport validation",
            "decoded_labels": ("only labels already shown to the agent when that request was made; any other token, "
                               "including the label of a journal observation the agent was never shown, passes through as written"),
        },
        "final_report_turn": {
            "trigger": final["trigger"],
            "offered_tools": ["final_answer"],
            "final_answer_description": FINAL_TURN_TOOL_DESCRIPTION,
            "response_contract": final["response_contract"],
            "response_format_hash": final["response_format_hash"],
            "schema_hash": final["schema_hash"],
            "input_admission": final["input_admission"],
            "admission_point": "before the turn is charged",
            "parsing": "native; an invalid output is not repaired",
            "business_call": "refused before dispatch (v1 check)",
        },
        "steps": {"max_steps": ALIGNED_STEPS,
                  "rule": "the episode actor-call cap must equal max_steps, so the final turn is a regular step"},
    }


def _request_messages(messages, tools, meter):
    """v1's request builder (external_agent._Bridge.generate), restated only to admit a final request before
    v1 charges it. _FinalTurnProvider refuses to send a final request that differs from this one."""
    public = []
    for message in messages:
        role = str(getattr(message.role, "value", message.role))
        payload = {"content": message.content}
        if message.tool_calls:
            payload["tool_calls"] = [{"name": c.function.name, "arguments": c.function.arguments, "id": c.id}
                                     for c in message.tool_calls]
        public.append({"role": role if role in ("system", "assistant", "user") else "user", "content": canonical_json(payload)})
    public.append({"role": "user", "content": canonical_json({
        "transport": TRANSPORT_CONTRACT,
        "tools": [{"name": t.name, "description": t.description, "inputs": t.inputs} for t in tools],
        "final_report_required": meter.final_turn,
        "remaining_actor_calls": meter.caps.actor_calls - meter.usage.actor_calls,
    })})
    return public


class _FinalTurnProvider:
    """Adds the native final-answer response contract to requests v2 flagged as the final turn, and nothing else.

    v1's request code (shared) calls provider.complete(messages, role=..., max_output_tokens=..., timeout_seconds=...);
    ordinary turns reach the provider with exactly those arguments.
    """
    def __init__(self, provider, bridge):
        self._provider, self._bridge = provider, bridge

    def __getattr__(self, name):
        return getattr(self._provider, name)

    async def complete(self, messages, **kwargs):
        # v2 reads the final-turn flag at the same point as v1's request builder; this confirms the request says so.
        if json.loads(messages[-1]["content"]).get("final_report_required") is not self._bridge.final_request:
            raise RuntimeError("Adapter v2 final-turn flag differs from its request")
        if self._bridge.final_request:
            if messages != self._bridge.admitted_request:
                raise RuntimeError("Adapter v2 final request differs from the request it admitted")
            kwargs = {**kwargs, "response_contract": NATIVE_FINAL_ANSWER_CONTRACT}
        return await self._provider.complete(messages, **kwargs)


class _BridgeV2(_Bridge):
    """v1's bridge (same transport, accounting, retry, stop and dispatch code) plus labels and the final turn."""

    def __init__(self, context, loop):
        context = copy(context)          # this episode's own view; broker, journal and meter are shared
        super().__init__(context, loop)
        context.provider = _FinalTurnProvider(context.provider, self)
        self.final_request = False
        self.admitted_request = None     # the final request admitted with its schema, before it was charged
        self.request_observations = []   # observations delivered by the time of the latest model request
        self.shown_labels = set()        # every label v2 has handed to the agent so far
        self.request_shown_labels = frozenset()   # labels already shown when the latest request was made

    def _journal_rows(self):
        return [o.model_dump(mode="json") for o in self.context.broker.journal.observations]

    def _shown(self, row, labels):
        """The row with its evidence_id replaced by its journal label (app.agents.progress.labelled_observations)."""
        if not isinstance(row, dict) or row.get("evidence_id") not in labels:
            return row
        label = labels[row["evidence_id"]]
        self.shown_labels.add(label)
        return {**row, "evidence_id": label}

    def _labelled(self, text):
        """Relabel a v1 business tool result; every other byte of it is unchanged."""
        value = json.loads(text)
        labels = evidence_labels(self._journal_rows())
        for field in LABELLED_FIELDS:
            if isinstance(value.get(field), dict):
                value[field] = self._shown(value[field], labels)
            elif isinstance(value.get(field), list):
                value[field] = [self._shown(row, labels) for row in value[field]]
        return canonical_json(value)

    async def generate(self, messages, tools):
        meter = self.context.broker.meter
        # Read exactly where v1's request builder reads it (before the turn is charged); nothing in between
        # can change it, and _FinalTurnProvider checks the built request agrees.
        self.final_request = meter.final_turn
        self.request_observations = self._journal_rows()
        # Every label v2 has handed over is in this request: smolagents keeps each tool result and each tool
        # error in the agent's memory, untruncated. Only these labels can be decoded from its answer.
        self.request_shown_labels = frozenset(self.shown_labels)
        self.admitted_request = None
        if self.final_request:
            tools = [SimpleNamespace(name=tool.name, description=FINAL_TURN_TOOL_DESCRIPTION, inputs=tool.inputs)
                     for tool in tools if tool.name == "final_answer"]
            # v1's first steps, in v1's order, then admission with the final-answer schema counted, before v1
            # charges the turn (the reference Actor's order). v1 then repeats its own steps and its own check.
            if self.fatal_provider_error is not None:
                raise self.fatal_provider_error
            meter.check()
            if self.closed.is_set():
                raise StopRequested()
            self.admitted_request = _request_messages(messages, tools, meter)
            validate_request_input(self.admitted_request, self.context.metadata["model_id"],
                                   response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
        return await super().generate(messages, tools)

    async def dispatch(self, name, arguments):
        if name == "final_answer":
            return await self._final_answer(arguments)
        return self._labelled(await super().dispatch(name, arguments))

    async def _final_answer(self, arguments):
        # v1's final_answer steps, in v1's order, with the label decode before validation.
        if self.fatal_provider_error is not None:
            raise self.fatal_provider_error
        context = self.context
        meter = context.broker.meter
        meter.check()
        if self.closed.is_set():
            raise StopRequested()
        proposal = new_id("proposal")
        if set(arguments) != {"answer"}:
            raise ActorReportError("Final answer requires the original report")
        answer = arguments["answer"]
        delivered, shown = self.request_observations, self.request_shown_labels
        cited = answer.get("evidence_ids") if isinstance(answer, dict) else None
        if isinstance(cited, list):
            # Exact and total, token by token, with the reference decoder over the journal as it stood at the
            # request (so a label keeps its journal position). Only a label already shown to the agent is
            # decoded; any other token -- including the label of an observation the agent never saw -- passes
            # through as written and fails as it would in v1.
            answer = {**answer, "evidence_ids": [decode_citations([token], delivered)[0]
                                                 if isinstance(token, str) and token in shown else token
                                                 for token in cited]}
        try:
            report = TaskReport.model_validate_json(canonical_json(answer))
        except ValidationError:
            # Decoding cannot change validity: a label and the ID it decodes to are both valid IDs, and every
            # other token and field is unchanged. So the answer as written fails in exactly the same places,
            # and the agent is shown that native error, which quotes its own tokens, never a decoded ID.
            TaskReport.model_validate_json(canonical_json(arguments["answer"]))
            raise
        result = await context.interpreter.invoke("before_final_report", proposal, ReportAction(kind="report", report=report))
        if result.blocked:
            now = evidence_labels(self._journal_rows())
            raise ValueError(canonical_json({"blocked_report": result.reasons, "observations": [
                self._shown(o.model_dump(mode="json"), now) for o in result.observations]}))
        labels = evidence_labels(delivered)
        order = {label: index for index, label in enumerate(labels.values())}
        unshown = set(labels.values()) - shown
        context.broker.journal.store.append_event(context.provenance.episode_id, tick=meter.usage.ticks, role="actor",
            type="report_submitted", payload={
                "report": report.model_dump(mode="json"),
                "adapter_entrypoint_id": ENTRYPOINT,
                "citation_protocol": PROTOCOL_VERSION,
                "cited_evidence_tokens": cited,
                "decoded_evidence_ids": report.evidence_ids,
                "evidence_labels": labels,
                "labels_shown_to_agent": sorted(shown, key=lambda label: order.get(label, len(order))),
                "cited_unshown_labels": [token for token in cited if token in unshown],
                "final_report_required": self.final_request,
                "response_contract": NATIVE_FINAL_ANSWER_CONTRACT if self.final_request else None})
        return report.model_dump(mode="json")


class SmolagentsActorV2:
    """Adapter v2: a new native agent, model wrapper and empty memory for every invocation."""
    def __init__(self, *, model_id):
        self.model_id = model_id

    async def __call__(self, intent, context):
        from app.adapters.decorator import track_faultlab
        adapted_context = copy(context)
        adapted_context.adapter_id = ENTRYPOINT
        tracked = track_faultlab(adapter_id=ENTRYPOINT)(self._run)
        return await tracked(intent, adapted_context)

    async def _run(self, intent, context):
        # v1's driver (external_agent.SmolagentsActor._run) with v2's bridge; see the module docstring.
        if context.metadata["model_id"] != self.model_id:
            raise ValueError("External model differs from frozen registration")
        if context.broker.meter.caps.actor_calls != ALIGNED_STEPS:
            raise ValueError("Adapter v2 steps differ from the episode actor-call cap")
        bridge = _BridgeV2(context, asyncio.get_running_loop())
        try:
            agent = _native_agent(bridge, self.model_id)
            task = canonical_json({"task": intent, "contract": TASK_CONTRACT})
            try:
                result = await asyncio.to_thread(agent.run, task, reset=True, max_steps=ALIGNED_STEPS)
            except Exception as error:
                if bridge.fatal_provider_error is not None:
                    raise bridge.fatal_provider_error from error
                original = error
                seen = set()
                while original is not None and id(original) not in seen:
                    seen.add(id(original))
                    if isinstance(original, (ActorReportError, BudgetExhausted, StopRequested, RuntimeProviderError)):
                        raise original
                    original = original.__cause__
                raise
            if bridge.fatal_provider_error is not None:
                raise bridge.fatal_provider_error
            try:
                return TaskReport.model_validate_json(canonical_json(result))
            except ValueError:
                raise ActorReportError("External agent produced no valid original final report") from None
        finally:
            bridge.close()


__all__ = ["ENTRYPOINT", "DISPLAY_NAME", "SmolagentsActorV2", "adapter_protocol", "TASK_CONTRACT", "TRANSPORT_CONTRACT"]
