"""The model-backed Actor adapter: the legacy reference Actor's prompt loop on the v2 session.

The port keeps what makes results comparable with the September program and the Claude screens:
the same system prompt (its hash is the adapter's prompt digest), the same action schema, the
same per-turn user message (``turn_message`` of the legacy ``app.agents.progress``, with every
delivered observation presented in the legacy ``PublicObservation`` shape and, under the indexed
protocol, named by its journal position), the same final-turn rule (the last allowed turn must
be a report), the same handling of an invalid answer (it costs a turn, the model is told, nothing
is repaired) and the same blind-retry rule (one retry of the identical request only when no
answer arrived). What differs is where the tools go: through the ``TrialSession`` (effectsafe
journal, kernel transport) instead of the legacy broker. Recovery policies run at one hook only,
the report gate (``faultlab.lab.rules``), and only when the adapter is given a ``rule_policy``;
without one the empty baseline policy is what the screens ran.

The provider is anything with the legacy ``RuntimeProvider.complete`` shape; the tests use a
scripted one, a live run passes the real one. Legacy modules are imported lazily, like the
referee bridge, so the identity of the prompt is the legacy file's and nothing is copied.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any, Protocol

from faultlab.adapters.base import AdapterSpec, BaseAdapter
from faultlab.core import content_hash
from faultlab.lab.rules import SUPPORTED_HOOKS, ReportGate, check_policy, policy_from_json
from faultlab.lab.session import CapExhausted, TrialSession
from faultlab.packs import load_pack

ADAPTER_ID = "model-actor"
VERSION = "1"
PROTOCOL_V1 = "faultlab-actor-context/v1"
PROTOCOL_V4 = "faultlab-actor-context/v4-indexed-evidence"
SUPPORTED_PROTOCOLS = (PROTOCOL_V1, PROTOCOL_V4)
MAX_OUTPUT_TOKENS = 2000
TURN_TIMEOUT_SECONDS = 20.0
PACK_ID = "orders.upgrade_then_confirm/v1"


class Provider(Protocol):
    async def complete(self, messages: list[dict[str, str]], *, role: str = "actor", max_output_tokens: int = MAX_OUTPUT_TOKENS,
                       timeout_seconds: float = TURN_TIMEOUT_SECONDS, response_contract: str | None = None): ...


def _legacy():
    try:
        from app.agents import actor, progress, transport_retry
        from app.contracts import models
        from app.providers import runtime
    except ImportError:
        backend = Path(__file__).resolve().parents[2] / "backend"
        if not (backend / "app" / "agents").is_dir():
            raise RuntimeError("The model Actor adapter needs the legacy backend/app beside this package") from None
        if str(backend) not in sys.path:
            sys.path.append(str(backend))
        from app.agents import actor, progress, transport_retry
        from app.contracts import models
        from app.providers import runtime
    return actor, progress, transport_retry, models, runtime


def legacy_observation(observation: dict, episode_id: str, models) -> dict:
    """One session observation in the legacy ``PublicObservation`` shape the Actor was always shown."""
    result = models.ToolResult.model_validate(observation["result"])
    data = result.data
    return models.PublicObservation(evidence_id=observation["evidence_id"], episode_id=episode_id, call_id=observation["call_id"],
                                    delivered_tick=min(int(observation["delivered_tick"]), 20), result=result,
                                    observed_operation_id=getattr(data, "operation_id", None),
                                    observed_order_id=getattr(data, "order_id", None),
                                    observed_intent_hash=getattr(data, "intent_hash", None),
                                    source_receipt_id=result.receipt_id).model_dump(mode="json")


class ModelActorAdapter(BaseAdapter):
    def __init__(self, provider: Provider, model: str, *, protocol: str = PROTOCOL_V4, turn_timeout_seconds: float = TURN_TIMEOUT_SECONDS,
                 rule_policy: Any = None):
        if protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"Unsupported actor context protocol {protocol!r}; this adapter runs {SUPPORTED_PROTOCOLS}")
        actor, progress, _, _, runtime = _legacy()
        self.provider, self.model, self.protocol, self.turn_timeout_seconds = provider, model, protocol, turn_timeout_seconds
        # A recovery-rule policy (effectsafe rules at the report gate) is part of what this agent carries: refused here
        # if it names a hook or an operation the gate does not run; it changes the settings digest.
        self.rule_policy = policy_from_json(rule_policy) if rule_policy is not None else None
        if self.rule_policy is not None:
            check_policy(self.rule_policy, load_pack(PACK_ID))
        descriptor = progress.actor_context_protocol(protocol)
        settings = {"actor_context_protocol": protocol, "actor_context_protocol_hash": descriptor["descriptor_hash"],
                    "actor_response_protocol": runtime.ACTOR_RESPONSE_PROTOCOL_VERSION,
                    "actor_response_protocol_hash": content_hash(runtime.actor_response_protocol()),
                    "max_output_tokens": MAX_OUTPUT_TOKENS, "turn_timeout_seconds": turn_timeout_seconds, "blind_retries": 1}
        if self.rule_policy is not None:
            settings["rule_policy"] = self.rule_policy.model_dump(mode="json")
            settings["rule_hooks"] = list(SUPPORTED_HOOKS)
        self.spec = AdapterSpec(adapter_id=ADAPTER_ID, version=VERSION, model=model, packs=[PACK_ID],
                                description="The legacy reference Actor's prompt loop on a model provider, through the v2 session.",
                                settings_digest=content_hash(settings), prompt_digest=actor.ACTOR_PROMPT_HASH)
        self.turns: list[dict] = []

    async def act(self, session: TrialSession):
        actor, progress, transport_retry, models, runtime = _legacy()
        i = session.intent
        caps = session.caps.model_calls if session.caps.model_calls is not None else 8
        messages = [{"role": "system", "content": actor.ACTOR_PROMPT},
                    {"role": "user", "content": models.canonical_json({"task": i, "output_schema": actor.ACTION_ADAPTER.json_schema()})}]
        episode_id = session.attempt_id
        gate = ReportGate(self.rule_policy, session.pack, session)
        gate.declare()
        while session.usage.model_calls < caps:
            final = session.usage.model_calls + 1 >= caps
            shown = [legacy_observation(o.model_dump(mode="json"), episode_id, models) for o in session.observations]
            user = progress.turn_message(shown, final_report_required=final, remaining_actor_calls=caps - session.usage.model_calls,
                                         protocol=self.protocol)
            call_messages = messages + [{"role": "user", "content": models.canonical_json(user)}]
            response_contract = "actor_final_report" if final else None
            runtime.validate_request_input(call_messages, self.model, response_contract=response_contract)
            generation = None
            session.model_call()                                   # one turn, charged before the request leaves
            for transport_attempt in range(2):
                try:
                    generation = await self.provider.complete(call_messages, role="actor", max_output_tokens=MAX_OUTPUT_TOKENS,
                                                              timeout_seconds=self.turn_timeout_seconds, response_contract=response_contract)
                    break
                except runtime.RuntimeProviderError as error:
                    if error.generation is not None:
                        session.account(input_tokens=error.generation.input_tokens or 0, output_tokens=error.generation.output_tokens or 0,
                                        dollars=error.generation.cost_usd)
                    else:
                        session.account(dollars=None)              # a charged request with no usage: the cost is unknown from here on
                    if transport_attempt == 0 and transport_retry.blind_retry_allowed(error):
                        if transport_retry.service_unavailable(error):
                            await asyncio.sleep(transport_retry.SERVICE_UNAVAILABLE_DELAY_SECONDS)
                        session.rule_step("model_transport_retry", transport_retry.retry_payload(error, transport_attempt + 1))
                        continue
                    raise
            session.account(input_tokens=generation.input_tokens or 0, output_tokens=generation.output_tokens or 0, dollars=generation.cost_usd)
            if generation.model_id != self.model:
                raise runtime.RuntimeProviderError("Provider returned a different frozen model")
            self.turns.append({"turn": session.usage.model_calls, "final_report_required": final,
                               "request_digest": content_hash(call_messages), "raw": generation.content})
            try:
                action = actor.ACTION_ADAPTER.validate_json(generation.content)
            except Exception as error:
                errors = ([{"location": list(issue["loc"]), "type": issue["type"]}
                           for issue in error.errors(include_input=False, include_context=False, include_url=False)]
                          if hasattr(error, "errors") else [{"location": [], "type": "invalid_json"}])
                messages.extend([{"role": "assistant", "content": generation.content},
                                 {"role": "user", "content": models.canonical_json({"action_errors": errors, "instruction":
                                     "Your action failed output_schema. Return exactly one allowed tool or report action with only its "
                                     "declared fields. No business call was executed; this correction consumes a turn."})}])
                continue
            if isinstance(action, models.ReportAction):
                report = action.report
                if self.protocol in progress.INDEXED_EVIDENCE_PROTOCOLS:
                    report = report.model_copy(update={"evidence_ids": progress.decode_citations(report.evidence_ids, shown)})
                proposal = report.model_dump(mode="json")
                verdict = await gate.check(proposal)
                if verdict is not None and verdict.blocked:
                    # A runtime rule refused the proposal: nothing was recorded, the model is told why, the turn is spent.
                    messages.extend([{"role": "assistant", "content": generation.content},
                                     {"role": "user", "content": models.canonical_json({"report_blocked": verdict.reasons,
                                         "rule_requirements": gate.last_requirements, "instruction":
                                         "A runtime rule refused this report; nothing was recorded. Re-read the delivered evidence and "
                                         "return a truthful report action; this correction consumes a turn."})}])
                    continue
                session.submit(proposal)
                return None
            if final:
                messages.append({"role": "user", "content": "A report was required on the reserved final turn; no business call executed."})
                continue
            try:
                await session.call(*self._request(action, i))
            except CapExhausted as error:
                if error.cap != "http_attempts":
                    raise
                messages.append({"role": "user", "content": "Business budget exhausted. Return your truthful final report from existing observations."})
        return None

    @staticmethod
    def _request(action, i: dict) -> tuple[str, dict]:
        tool = action.tool
        if tool == "get_order":
            return tool, {"order_id": i["order_id"]}
        if tool == "get_operation_status":
            service = action.arguments.service
            return tool, {"service": service, "operation_id": i["upgrade_operation_id" if service == "orders" else "notification_operation_id"]}
        if tool == "update_order":
            return tool, {"order_id": i["order_id"], "operation_id": i["upgrade_operation_id"], "payload": {
                "order_id": i["order_id"], "desired_shipping": "express", "expected_version": i["expected_version"],
                "operation_id": i["upgrade_operation_id"], "idempotency_key": i["upgrade_idempotency_key"], "intent_hash": i["upgrade_intent_hash"]}}
        return tool, {"order_id": i["order_id"], "operation_id": i["notification_operation_id"], "payload": {
            "order_id": i["order_id"], "upgrade_operation_id": i["upgrade_operation_id"], "operation_id": i["notification_operation_id"],
            "idempotency_key": i["notification_idempotency_key"], "intent_hash": i["notification_intent_hash"], "template_version": "confirmation/v1"}}


__all__ = ["ADAPTER_ID", "ModelActorAdapter", "PROTOCOL_V1", "PROTOCOL_V4", "Provider", "SUPPORTED_PROTOCOLS", "legacy_observation"]
