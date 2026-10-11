"""The trial session: what an adapter is lent while its agent acts on one world.

The session is the broker of the legacy lab rebuilt on effectsafe: every write is prepared in the
journal (bytes pinned, identity kept), every dispatch is journalled before it reaches the
transport, every reply is reconciled into the operation's outcome, and everything the agent was
shown becomes an agent-visible evidence event. Caps are enforced here: a transport attempt or a
model call beyond the plan's caps raises ``CapExhausted``. A write the provider could not
recognise is refused by the journal (``UnsafeResend``); the session never works around that.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, JsonValue

from effectsafe import Evidence, Intent, Journal, JournalError, OperationState
from faultlab.core import Caps, FaultLabError, StrictModel, canonical_json, content_hash, new_id, utc_now_text
from faultlab.evidence.models import EvidenceEvent, hashed_payload
from faultlab.lab.transport import TIMEOUT_CODE, KernelTransport, TransportResult

RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
RETRYABLE_CODES = frozenset({"TRANSIENT_UNAVAILABLE", "TRANSIENT_ERROR", "TEMPORARY_UNAVAILABLE", "SERVICE_UNAVAILABLE"})


class CapExhausted(FaultLabError):
    """A declared cap was reached: the session takes no further action of that kind."""

    def __init__(self, cap: str, limit):
        super().__init__(f"{cap} cap of {limit} reached")
        self.cap, self.limit = cap, limit


class ProtocolError(FaultLabError, ValueError):
    """The adapter asked for something the pack does not declare."""


class Observation(StrictModel):
    """What one transport attempt delivered to the agent, verbatim."""
    evidence_id: str
    call_id: str
    attempt_id: str
    tool: str
    transport: Literal["ok", "timeout", "error"]
    http_status: int | None = None
    result: JsonValue
    delivered_tick: int = Field(ge=0)


class Usage(StrictModel):
    model_calls: int = 0
    http_attempts: int = 0
    waits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    dollars_measured: float | None = 0.0       # None once any paid call reported no cost
    ticks: int = 0


class TrialSession:
    def __init__(self, *, pack, plan, attempt_id: str, world_id: str, intent: dict, transport: KernelTransport,
                 journal: Journal, caps: Caps, max_attempts_per_call: int = 2):
        self.pack, self.plan, self.attempt_id, self.world_id = pack, plan, attempt_id, world_id
        self.intent, self.transport, self.journal, self.caps = intent, transport, journal, caps
        self.max_attempts_per_call = max_attempts_per_call
        self.usage = Usage()
        self.observations: list[Observation] = []
        self.calls: list[dict] = []
        self.events: list[EvidenceEvent] = []
        self.report: Any = None
        self.report_submitted = False
        self.closed = False

    # -- what the adapter may know ------------------------------------------------------------------

    @property
    def tools(self):
        return self.pack.tools

    def operation(self, operation_id: str) -> OperationState:
        """The journal's outcome for an operation; one never prepared is NOT_STARTED with no attempts."""
        try:
            return self.journal.operation(operation_id)["state"]
        except JournalError:
            return OperationState()

    def remaining(self) -> dict:
        return {"model_calls": None if self.caps.model_calls is None else self.caps.model_calls - self.usage.model_calls,
                "http_attempts": None if self.caps.http_attempts is None else self.caps.http_attempts - self.usage.http_attempts}

    # -- evidence --------------------------------------------------------------------------------------

    def _event(self, kind: str, payload: dict, *, plane="agent_visible", operation_id=None, attempt_ref=None) -> EvidenceEvent:
        event = EvidenceEvent(seq=len(self.events), plane=plane, kind=kind, source="lab", certainty="observed",
                              operation_id=operation_id, attempt_ref=attempt_ref, logical_time=self.usage.ticks,
                              wall_time=utc_now_text(), clock="session", clock_sequence=len(self.events),
                              **hashed_payload(payload), source_ref=f"/events/{len(self.events)}")
        self.events.append(event)
        return event

    # -- accounting ----------------------------------------------------------------------------------

    def model_call(self, *, input_tokens: int = 0, output_tokens: int = 0, dollars: float | None = 0.0) -> None:
        """Charge one model call before it is made; a cap reached is refused, never silently exceeded."""
        self._require_open()
        if self.caps.model_calls is not None and self.usage.model_calls >= self.caps.model_calls:
            raise CapExhausted("model_calls", self.caps.model_calls)
        self.usage.model_calls += 1
        self.account(input_tokens=input_tokens, output_tokens=output_tokens, dollars=dollars)

    def account(self, *, input_tokens: int = 0, output_tokens: int = 0, dollars: float | None = 0.0) -> None:
        self.usage.input_tokens += int(input_tokens)
        self.usage.output_tokens += int(output_tokens)
        if dollars is None:
            self.usage.dollars_measured = None
        elif self.usage.dollars_measured is not None:
            self.usage.dollars_measured += float(dollars)
        if self.caps.dollars is not None and self.usage.dollars_measured is not None and self.usage.dollars_measured > self.caps.dollars:
            raise CapExhausted("dollars", self.caps.dollars)

    def _http_attempt(self) -> None:
        if self.caps.http_attempts is not None and self.usage.http_attempts >= self.caps.http_attempts:
            raise CapExhausted("http_attempts", self.caps.http_attempts)
        self.usage.http_attempts += 1

    def _require_open(self):
        if self.closed:
            raise ProtocolError("The session is closed")

    # -- acting ----------------------------------------------------------------------------------------

    async def call(self, tool: str, request: dict | None = None, *, caller: str = "agent", hook: str | None = None) -> Observation:
        """One logical call: journalled, dispatched up to ``max_attempts_per_call`` times, every reply recorded.

        ``request`` carries what the pack's routes carry: identities (``order_id``, ``operation_id``,
        ``service``) and, for a write, ``payload``. The pinned bytes are the canonical payload.
        """
        self._require_open()
        try:
            contract = self.pack.tool(tool)
            request = dict(request or {})
            service = self.pack.service(tool, request)
        except ValueError as error:                       # an undeclared tool or service: the adapter broke the protocol
            raise ProtocolError(str(error)) from error
        payload = request.get("payload")
        if contract.kind == "write" and not isinstance(payload, dict):
            raise ProtocolError(f"{tool} is a write and needs a payload")
        call_id = new_id("call")
        scope = str(request.get("order_id") or request.get("scope") or self.world_id)
        if contract.kind == "write":
            operation_id = str(request.get("operation_id") or payload.get("operation_id") or new_id("operation"))
            intent = Intent(operation_id=operation_id, action=tool, scope=scope, payload=payload)
        else:
            operation_id = f"read-{call_id}"
            intent = Intent(operation_id=operation_id, action=tool, scope=scope,
                            payload={key: value for key, value in request.items() if key != "payload" and value is not None})
        operation = self.journal.prepare(intent, contract)
        # A read that is some write's status lookup reports on that write: its evidence folds into the write's outcome.
        reports_on = None
        if contract.kind == "read" and isinstance(request.get("operation_id"), str):
            try:
                target = self.journal.operation(request["operation_id"])
                if target["contract"].kind == "write" and target["contract"].status_lookup == tool:
                    reports_on = request["operation_id"]
            except Exception:
                reports_on = None
        attempts, observation = [], None
        try:
            for retry in range(self.max_attempts_per_call):
                self._http_attempt()
                attempt_id, pinned = self.journal.dispatch(operation_id)       # may raise UnsafeResend: the point of the layer
                attempts.append(attempt_id)
                self._event("invoked", {"tool": tool, "service": service, "call_id": call_id, "attempt_id": attempt_id,
                                        "caller": caller, "hook": hook, "bytes_digest": content_hash(pinned)},
                            operation_id=operation_id if contract.kind == "write" else None, attempt_ref=attempt_id)
                wire = {**{key: value for key, value in request.items() if key != "payload"}}
                wire["payload"] = canonical_payload(pinned) if contract.kind == "write" else None
                result = self.transport.send(self.world_id, tool=tool, service=service, request=wire, call_id=call_id, attempt_id=attempt_id)
                self.usage.ticks = self.transport.state(self.world_id)["tick"]
                observation = self._deliver(call_id, attempt_id, tool, contract, operation_id, result, reports_on)
                retryable = result.transport != "ok" or result.status in RETRYABLE_STATUSES or result.error_code in RETRYABLE_CODES
                if not retryable or retry + 1 >= self.max_attempts_per_call:
                    break
        finally:
            if attempts:
                self.calls.append({"call_id": call_id, "tool": tool, "service": service, "caller": caller, "hook": hook,
                                   "operation_id": operation_id if contract.kind == "write" else None, "attempt_ids": attempts,
                                   "observation_ids": [o.evidence_id for o in self.observations if o.call_id == call_id]})
        return observation

    def _deliver(self, call_id, attempt_id, tool, contract, operation_id, result: TransportResult, reports_on: str | None) -> Observation:
        body = result.body if isinstance(result.body, dict) else None
        if result.transport == "ok" and body is not None:
            evidence = Evidence(transport="ok", status=body.get("status") if isinstance(body.get("status"), str) else None,
                                receipt_id=body.get("receipt_id") if isinstance(body.get("receipt_id"), str) else None,
                                error_code=result.error_code)
            shown = body
        else:
            code = result.error_code or ("HTTP_TIMEOUT" if result.transport == "timeout" else "TRANSPORT_ERROR")
            evidence = Evidence(transport="timeout" if result.transport == "timeout" else "error", error_code=code)
            shown = {"call_id": call_id, "tool": tool, "transport": "timeout" if result.transport == "timeout" else "error",
                     "operation_id": operation_id if contract.kind == "write" else None, "error_code": code}
        state = self.journal.deliver(attempt_id, evidence)
        outcome_of = operation_id if contract.kind == "write" else None
        if reports_on is not None:
            state = self.journal.observe(reports_on, evidence, source_attempt_id=attempt_id)
            outcome_of = reports_on
        observation = Observation(evidence_id=new_id("evidence"), call_id=call_id, attempt_id=attempt_id, tool=tool,
                                  transport=shown["transport"] if isinstance(shown.get("transport"), str) else "ok",
                                  http_status=result.status, result=shown, delivered_tick=self.usage.ticks)
        self.observations.append(observation)
        self._event("response_delivered", {"observation": observation.model_dump(mode="json"),
                                           "outcome": state.outcome if outcome_of else None, "reports_on": outcome_of,
                                           "reply_delay_seconds": result.delay},
                    operation_id=outcome_of, attempt_ref=attempt_id)
        return observation

    async def wait(self, ticks: int, *, caller: str = "agent", hook: str | None = None) -> int:
        self._require_open()
        tick = self.transport.advance(self.world_id, ticks)
        self.usage.waits += 1
        self.usage.ticks = tick
        self._event("waited", {"ticks": ticks, "tick": tick, "caller": caller, "hook": hook})
        return tick

    def rule_step(self, hook: str, payload: dict) -> None:
        """Record a recovery-rule step an integration ran (effectsafe rules) as agent-visible evidence."""
        self._event("rule_step", {"hook": hook, **payload})

    def submit(self, report: Any) -> None:
        """Record the agent's final report exactly as handed over; validity is the referee's question."""
        self._require_open()
        if self.report_submitted:
            raise ProtocolError("A session takes one report")
        if isinstance(report, StrictModel) or hasattr(report, "model_dump"):
            report = report.model_dump(mode="json")
        self.report, self.report_submitted = report, True
        interpreted = None
        try:
            interpreted = self.pack.report_model.model_validate(report).model_dump(mode="json")
        except (TypeError, ValueError):
            pass
        self._event("claim", {"report": report, "valid_shape": interpreted is not None})

    def close(self) -> None:
        self.closed = True


def canonical_payload(pinned: str) -> dict:
    import json
    return json.loads(pinned)


__all__ = ["CapExhausted", "Observation", "ProtocolError", "RETRYABLE_CODES", "RETRYABLE_STATUSES", "TrialSession", "Usage"]
