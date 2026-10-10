"""Parent-owned business semantics for a native agent in a bounded process."""
from __future__ import annotations

import asyncio
from copy import copy

from pydantic import ValidationError

from app.agents.actor import ActorReportError
from app.contracts.models import ReportAction, TaskReport, canonical_json, new_id
from app.integrations.external_agent_v2 import _BridgeV2, PROTOCOL_VERSION as CITATION_PROTOCOL
from app.lab.budgets import StopRequested

ENTRYPOINT = "smolagents-user-code-v1"
MODEL_ID = "faultlab-native-orders-double/v1"


class NativeReportBlocked(ValueError):
    def __init__(self, public_payload):
        self.public_payload = public_payload
        super().__init__("Native report blocked by policy")


class NativeBridge(_BridgeV2):
    """Reuse reviewed model accounting, hooks, dispatch, and shown-only labels.

    The final tool result is provisional. The native worker must return it
    unchanged and exit cleanly before an episode report is submitted.
    """
    def __init__(self, context, record):
        super().__init__(context, asyncio.get_running_loop())
        self.record = record
        self.pending = None

    async def _final_answer(self, arguments):
        if self.fatal_provider_error is not None:
            raise self.fatal_provider_error
        context = self.context
        meter = context.broker.meter
        meter.check()
        if self.closed.is_set():
            raise StopRequested()
        if set(arguments) != {"answer"}:
            raise ActorReportError("Final answer requires the original report")
        original = arguments["answer"]
        shown = dict(self.request_labels)
        answer = original
        cited = answer.get("evidence_ids") if isinstance(answer, dict) else None
        if isinstance(cited, list):
            answer = {**answer, "evidence_ids": [shown.get(token, token) if isinstance(token, str) else token for token in cited]}
        try:
            report = TaskReport.model_validate_json(canonical_json(answer))
        except ValidationError:
            TaskReport.model_validate_json(canonical_json(original))
            raise
        result = await context.interpreter.invoke("before_final_report", new_id("proposal"),
                                                  ReportAction(kind="report", report=report))
        if result.blocked:
            # No evaluator truth or unshown IDs are included in a native error.
            journal = self._journal_ids()
            raise NativeReportBlocked({"blocked_report": result.reasons, "observations": [
                self._shown(observation.model_dump(mode="json"), journal) for observation in result.observations]})
        payload = {"report": report.model_dump(mode="json"), "adapter_entrypoint_id": ENTRYPOINT,
                   "citation_protocol": CITATION_PROTOCOL, "cited_evidence_tokens": cited,
                   "decoded_evidence_ids": report.evidence_ids,
                   "evidence_labels": {evidence_id: label for label, evidence_id in shown.items()},
                   "labels_shown_to_agent": list(shown),
                   "cited_tokens_not_decoded": [token for token in cited if not (isinstance(token, str) and token in shown)],
                   "final_report_required": self.final_request}
        self.pending = {"original_report": original, "decoded_report": report.model_dump(mode="json"),
                        "submission_event": payload, "delivery_status": "PROVISIONAL"}
        self.record["final_report"] = self.pending
        return report.model_dump(mode="json")

    def submit(self):
        if self.pending is None or self.pending["delivery_status"] != "PROVISIONAL":
            raise ActorReportError("Native worker did not complete its original report")
        self.context.broker.meter.check()
        self.context.broker.journal.store.append_event(self.context.provenance.episode_id,
            tick=self.context.broker.meter.usage.ticks, role="actor", type="report_submitted",
            payload=self.pending["submission_event"])
        self.pending["delivery_status"] = "RETURNED_TO_RUNNER"
        return TaskReport.model_validate_json(canonical_json(self.pending["decoded_report"]))


class NativeActor:
    def __init__(self, provider):
        self.provider = provider

    async def __call__(self, intent, context):
        from app.adapters.decorator import track_faultlab
        adapted = copy(context)
        adapted.adapter_id = ENTRYPOINT
        return await track_faultlab(adapter_id=ENTRYPOINT)(self._run)(intent, adapted)

    async def _run(self, intent, context):
        if context.provider is not self.provider or context.metadata["model_id"] != MODEL_ID:
            raise ValueError("Native execution differs from its explicit frozen binding")
        if context.broker.meter.caps.actor_calls != 8:
            raise ValueError("Native step count differs from the reviewed episode budget")
        return await self.provider.execute(intent, context)
