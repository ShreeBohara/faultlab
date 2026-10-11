"""Fault schedules generic over ``(tool, service, occurrence)`` with honest trigger accounting.

The kernel knows four families. F4 (transient failure before admission) and F1 (reply lost
after the effect committed) are placed by the kernel itself in ``dispatch``. F2 (asynchronous
completion) and F3 (stale read) need business meaning, so the handler places them inside
``perform`` using the matches the kernel hands it. Parameters are validated by the handler
(``validate_schedule``), which also decides which tools and services exist.
"""

from typing import Literal

from pydantic import Field, JsonValue

from faultlab.core.model import StrictModel
from faultlab.env.kernel.storage import event

Family = Literal["F1", "F2", "F3", "F4"]


class Primitive(StrictModel):
    kind: Family
    target_tool: str = Field(min_length=1, max_length=80)
    target_service: str = Field(min_length=1, max_length=80)
    occurrence: int = Field(ge=1, le=18)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class FaultSpec(StrictModel):
    schema_version: Literal["faultlab/v1"] = "faultlab/v1"
    scope: str = Field(default="orders.upgrade_then_confirm/v1", min_length=1, max_length=200)
    seed: int = Field(ge=0, le=2147483647)
    primitives: list[Primitive] = Field(default_factory=list, max_length=2)


def initial_executions(spec: dict) -> list[dict]:
    return [{"fault_id": f"fault-{index + 1}", "scheduled": True, "triggered": False, "trigger_tick": None,
             "call_id": None, "attempt_id": None, "reason": "target_not_reached"}
            for index, _ in enumerate(spec["primitives"])]


def matching(state: dict, tool: str, service: str) -> list[tuple[int, dict]]:
    """Count this call as the next occurrence of ``tool`` on ``service``; return the placements it hits."""
    key = tool + ":" + service
    occurrence = state["occurrences"].get(key, 0) + 1
    state["occurrences"][key] = occurrence
    found = []
    for index, primitive in enumerate(state["fault_spec"]["primitives"]):
        if primitive["target_tool"] != tool or primitive["target_service"] != service:
            continue
        count = primitive["parameters"].get("failure_count", 1) if primitive["kind"] == "F4" else 1
        if primitive["occurrence"] <= occurrence < primitive["occurrence"] + count:
            found.append((index, primitive))
    return found


def trigger(state: dict, index: int, call_id: str, attempt_id: str) -> None:
    record = state["fault_executions"][index]
    if not record["triggered"]:
        record.update(triggered=True, trigger_tick=state["tick"], call_id=call_id, attempt_id=attempt_id, reason=None)
    event(state, "fault_triggered", {"fault_id": record["fault_id"], "attempt_id": attempt_id}, call_id)


def prevented(state: dict, index: int, reason: str) -> None:
    if not state["fault_executions"][index]["triggered"]:
        state["fault_executions"][index]["reason"] = reason
