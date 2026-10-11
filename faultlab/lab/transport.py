"""Transports: how a session's request reaches a world and what comes back.

``KernelTransport`` runs a pack's world in this process on the kernel's own ``WorldStore`` and
``dispatch``. A lost reply is decided, not raced: the kernel returns the delay a fault adds to a
reply, and a delay beyond the session's timeout is reported as a timeout while the committed
effect is already durable (the transaction closed before the delay applies). That is the legacy
socket timeout without the wall clock, so a stale-read or lost-reply trial is reproducible and
cannot drift. An HTTP transport to a running service is a later phase.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from faultlab.core.model import StrictModel
from faultlab.env.kernel import KernelLimits, WorldError, WorldStore, dispatch

TIMEOUT_CODE = "HTTP_TIMEOUT"


class TransportResult(StrictModel):
    transport: Literal["ok", "timeout", "error"]
    status: int | None = None                      # the HTTP status the service answered with, when it answered
    body: JsonValue | None = None                  # the tool result exactly as the service produced it
    error_code: str | None = Field(default=None, max_length=80)
    delay: float = Field(default=0.0, ge=0)         # the reply delay the kernel declared (seconds)


class KernelTransport:
    def __init__(self, store: WorldStore, limits: KernelLimits | None = None, *, timeout_seconds: float = 1.0):
        self.store = store
        self.limits = limits or KernelLimits()
        self.timeout_seconds = timeout_seconds
        self._capabilities: dict[str, str] = {}

    @property
    def descriptor(self) -> dict:
        return {"kind": "kernel_in_process", "timeout_seconds": self.timeout_seconds, "limits": self.limits.model_dump(mode="json")}

    def create(self, episode_id: str, intent: dict, fault_spec: dict, fixture_id: str) -> dict:
        handle = self.store.create(episode_id, intent, fault_spec, fixture_id)
        self._capabilities[handle["world_id"]] = handle["capability"]
        return handle

    def send(self, world_id: str, *, tool: str, service: str, request: dict, call_id: str, attempt_id: str) -> TransportResult:
        capability = self._capabilities.get(world_id)
        if capability is None:
            return TransportResult(transport="error", error_code="UNKNOWN_WORLD")
        try:
            status, body, delay = dispatch(self.store, self.limits, world=world_id, capability=capability, call=call_id,
                                           attempt=attempt_id, tool=tool, service=service, request=request)
        except WorldError as error:
            # A refusal the kernel raised outside the handler's reply path (bad capability, unknown world).
            return TransportResult(transport="ok", status=error.status, body={"call_id": call_id, "tool": tool, "transport": "error",
                                                                              "error_code": error.code}, error_code=error.code)
        if delay > self.timeout_seconds:
            return TransportResult(transport="timeout", error_code=TIMEOUT_CODE, delay=float(delay))
        error_code = body.get("error_code") if isinstance(body, dict) else None
        return TransportResult(transport="ok", status=status, body=body, error_code=error_code if isinstance(error_code, str) else None,
                               delay=float(delay))

    def advance(self, world_id: str, ticks: int, *, observer: bool = False) -> int:
        from faultlab.env.kernel.clock import advance
        from faultlab.env.kernel.storage import event
        with self.store.transaction(world_id) as state:
            if not observer and (ticks > self.limits.wait_ticks or state["waits"] >= self.limits.waits):
                raise WorldError("WAIT_BUDGET", 429)
            advance(state, ticks, handler=self.store.handler, limits=self.limits, observer=observer)
            if not observer:
                state["waits"] += 1
            event(state, "observer_advanced" if observer else "wait_advanced", {"ticks": ticks})
            return state["tick"]

    def stop(self, world_id: str) -> int:
        from faultlab.env.kernel.storage import event
        with self.store.transaction(world_id) as state:
            if not state["stopped"]:
                state["stopped"] = True
                state["decision_tick"] = state["tick"]
                event(state, "world_stopped")
            return state["tick"]

    def state(self, world_id: str) -> dict:
        return self.store.read(world_id)

    def snapshot(self, world_id: str):
        return self.store.snapshot(world_id)

    def faults(self, world_id: str) -> list[dict]:
        return self.store.read(world_id)["fault_executions"]

    def events(self, world_id: str) -> list[dict]:
        return self.store.read(world_id)["events"]


__all__ = ["TIMEOUT_CODE", "KernelTransport", "TransportResult"]
