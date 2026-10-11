"""Coordinator-only controls over loopback with a shared capability. Never an agent tool."""

import ipaddress
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import Field, JsonValue

from faultlab.core.model import StrictModel
from faultlab.env.kernel.clock import advance
from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.faults import FaultSpec, initial_executions
from faultlab.env.kernel.storage import event


class CreateWorld(StrictModel):
    episode_id: str = Field(min_length=1, max_length=128)
    intent: dict[str, JsonValue]
    fault_spec: FaultSpec
    fixture_id: str = "standard-v1"


class Advance(StrictModel):
    ticks: int = Field(ge=1, le=5)
    observer: bool = False


def router(store, control_token, limits):
    api = APIRouter(prefix="/control")

    def authorize(request: Request, x_faultlab_control: str | None = Header(default=None)):
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == "testclient"
        if not local or not control_token or not x_faultlab_control or not secrets.compare_digest(control_token, x_faultlab_control):
            raise HTTPException(403, "Control capability required")
    api.dependencies = [Depends(authorize)]

    @api.get("/ready")
    def ready():
        return {"status": "ok", "service": "faultlab-simulator", "schema_version": "faultlab/v1", "pack": store.handler.pack_id}

    @api.post("/worlds", status_code=201)
    def create(body: CreateWorld):
        return store.create(body.episode_id, body.intent, body.fault_spec.model_dump(mode="json"), body.fixture_id)

    @api.get("/worlds/{world_id}/snapshot")
    def snapshot(world_id: str):
        return store.snapshot(world_id)

    @api.get("/worlds/{world_id}/faults")
    def faults(world_id: str):
        return store.read(world_id)["fault_executions"]

    @api.post("/worlds/{world_id}/faults")
    def install(world_id: str, body: FaultSpec):
        with store.transaction(world_id) as state:
            if state["tick"] or state["stopped"]:
                raise WorldError("WORLD_ALREADY_STARTED")
            spec = body.model_dump(mode="json")
            store.handler.validate_schedule(spec, state)
            state["fault_spec"] = spec
            state["fault_executions"] = initial_executions(spec)
        return {"installed": True}

    @api.post("/worlds/{world_id}/advance")
    def wait(world_id: str, body: Advance):
        with store.transaction(world_id) as state:
            if not body.observer and (body.ticks > limits.wait_ticks or state["waits"] >= limits.waits):
                raise WorldError("WAIT_BUDGET", 429)
            advance(state, body.ticks, handler=store.handler, limits=limits, observer=body.observer)
            if not body.observer:
                state["waits"] += 1
            event(state, "observer_advanced" if body.observer else "wait_advanced", {"ticks": body.ticks})
            tick = state["tick"]
        return {"tick": tick}

    @api.post("/worlds/{world_id}/stop")
    def stop(world_id: str):
        with store.transaction(world_id) as state:
            if not state["stopped"]:
                state["stopped"] = True
                state["decision_tick"] = state["tick"]
                event(state, "world_stopped")
            tick = state["tick"]
        return {"stopped": True, "tick": tick}

    store.handler.extend_control(api, store)
    return api
