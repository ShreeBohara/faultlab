"""Admission of one business request: budget, tick, attempt, fault placement, event log.

The order of decisions is the legacy simulator's and is part of what the lab proves:
pack hooks (diagnostic fixtures) run first; a transient failure (F4) is refused before any
effect and prevents a lost reply (F1) on the same call; a lost reply is only triggered when
the handler reports a committed effect, and otherwise recorded as prevented.
"""

from dataclasses import dataclass
import re

from faultlab.env.kernel.clock import advance
from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.faults import matching, prevented, trigger
from faultlab.env.kernel.storage import event

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


@dataclass
class DispatchContext:
    """What a handler may do during one admitted request, without touching kernel bookkeeping."""
    state: dict
    call_id: str
    attempt_id: str

    def trigger(self, index: int) -> None:
        trigger(self.state, index, self.call_id, self.attempt_id)

    def prevented(self, index: int, reason: str) -> None:
        prevented(self.state, index, reason)

    def event(self, event_type: str, payload: dict | None = None) -> dict:
        return event(self.state, event_type, payload, self.call_id)


def _transport_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not _ID.fullmatch(value):
        raise WorldError("INVALID_TRANSPORT_ID", 422)
    return value


def dispatch(store, limits, *, world: str, capability: str, call: str, attempt: str, tool: str, service: str,
             request: dict) -> tuple[int, dict, float]:
    """Admit and perform one request; returns ``(status, result_json, delay_seconds)``.

    The delay is applied by the caller after the transaction closes, so a lost-reply fault
    produces a genuine socket timeout while the committed effect is already durable.
    """
    handler = store.handler
    store.authorize(world, capability)
    _transport_id(call)
    _transport_id(attempt)
    delay = 0.0
    with store.transaction(world) as state:
        if state["stopped"]:
            raise WorldError("WORLD_STOPPED")
        if state["attempts"] >= limits.http_attempts or state["tick"] >= limits.ticks:
            raise WorldError("BUSINESS_BUDGET", 429)
        ctx = DispatchContext(state, call, attempt)
        advance(state, 1, handler=handler, limits=limits, ctx=ctx)
        state["attempts"] += 1
        event(state, "http_attempt", {"attempt_id": attempt, "tool": tool, "service": service}, call)
        faults = matching(state, tool, service)
        transient = next(((index, primitive) for index, primitive in faults if primitive["kind"] == "F4"), None)
        try:
            delay = max(delay, float(handler.before_perform(ctx, state, tool, service, request) or 0.0))
            if transient:
                ctx.trigger(transient[0])
                for index, primitive in faults:
                    if primitive["kind"] == "F1":
                        ctx.prevented(index, "pre_effect_failure")
                raise WorldError("TRANSIENT_UNAVAILABLE", 503)
            status, result, committed = handler.perform(ctx, state, tool, service, request, faults)
            for index, primitive in faults:
                if primitive["kind"] == "F1":
                    if committed:
                        ctx.trigger(index)
                        delay = max(delay, primitive["parameters"]["response_delay_ms"] / 1000)
                    else:
                        ctx.prevented(index, "target_not_committed")
        except WorldError as error:
            status, result = error.status, handler.error_result(call, tool, request, error.code)
            delay = max(delay, float(error.delay or 0.0))
            event(state, "request_rejected", {"error_code": error.code, "attempt_id": attempt}, call)
    return status, result, delay
