"""Wire models of the orders pack (``orders.upgrade_then_confirm/v1``), byte-compatible with v1.

Field sets and constraints mirror ``backend/app/contracts/models.py`` so the kernel-hosted
orders world answers exactly as the legacy simulator did. Nothing here imports ``app``.
"""

from typing import Annotated, Literal, Union

from pydantic import Field, JsonValue, model_validator

from faultlab.core.ids import Digest, Id
from faultlab.core.model import StrictModel

VERSION = "faultlab/v1"
SCOPE = "orders.upgrade_then_confirm/v1"
Service = Literal["orders", "notifications"]
Tool = Literal["get_order", "update_order", "get_operation_status", "send_confirmation"]
Status = Literal["PENDING", "SUCCEEDED", "FAILED", "UNKNOWN"]
StoredStatus = Literal["PENDING", "SUCCEEDED", "FAILED"]
SERVICE_OF_TOOL = {"get_order": "orders", "update_order": "orders", "send_confirmation": "notifications"}


class TaskIntent(StrictModel):
    schema_version: Literal["faultlab/v1"] = VERSION
    task_id: Id
    order_id: Id
    desired_shipping: Literal["express"] = "express"
    expected_version: int = Field(ge=1, le=1000000)
    template_version: Literal["confirmation/v1"] = "confirmation/v1"
    upgrade_operation_id: Id
    notification_operation_id: Id
    upgrade_idempotency_key: Id
    notification_idempotency_key: Id
    upgrade_intent_hash: Digest
    notification_intent_hash: Digest
    task_text: str = Field(min_length=1, max_length=2000)


class Receipt(StrictModel):
    receipt_id: Id
    operation_id: Id
    service: Service
    order_id: Id
    intent_hash: Digest
    status: Literal["SUCCEEDED", "FAILED"]
    terminal_tick: int = Field(ge=0, le=25)
    committed_version: int | None = Field(default=None, ge=1)
    effect_id: Id | None = None
    failure_code: Literal["UPGRADE_REJECTED", "VERSION_CONFLICT"] | None = None


class Order(StrictModel):
    order_id: Id
    applied_shipping: Literal["standard", "express"]
    requested_shipping: Literal["standard", "express"]
    version: int = Field(ge=1)
    last_upgrade_operation_id: Id | None = None


class OperationData(StrictModel):
    operation_id: Id
    service: Service
    order_id: Id
    intent_hash: Digest
    status: Status
    receipt: Receipt | None = None


class ToolResult(StrictModel):
    call_id: Id
    tool: Tool
    transport: Literal["ok", "timeout", "error"]
    operation_id: Id | None = None
    order_id: Id | None = None
    status: Status | None = None
    observed_version: int | None = Field(default=None, ge=1)
    receipt_id: Id | None = None
    retry_after_ticks: int | None = Field(default=None, ge=1, le=20)
    error_code: str | None = Field(default=None, max_length=80)
    data: Order | OperationData | None = None


class Operation(StrictModel):
    schema_version: Literal["faultlab/v1"] = VERSION
    operation_id: Id
    service: Service
    task_id: Id
    order_id: Id
    payload_hash: Digest
    state: StoredStatus
    accepted_tick: int = Field(ge=0, le=20)
    terminal_tick: int | None = Field(default=None, ge=0, le=25)
    receipt: Receipt | None = None


class NotificationEffect(StrictModel):
    schema_version: Literal["faultlab/v1"] = VERSION
    notification_id: Id
    order_id: Id
    upgrade_operation_id: Id
    operation_id: Id
    idempotency_key: Id
    payload_hash: Digest
    created_tick: int = Field(ge=0, le=25)
    template_version: Literal["confirmation/v1"] = "confirmation/v1"


class EventRecord(StrictModel):
    schema_version: Literal["faultlab/v1"] = VERSION
    episode_id: Id
    seq: int = Field(ge=1)
    tick: int = Field(ge=0, le=25)
    at: str
    role: str
    type: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    call_id: Id | None = None
    evidence_id: Id | None = None
    visibility: Literal["PUBLIC_OBSERVATION", "DEVELOPMENT_DIAGNOSTIC", "PRIVATE_EVALUATOR"]


class WorldSnapshot(StrictModel):
    schema_version: Literal["faultlab/v1"] = VERSION
    world_id: Id
    tick: int = Field(ge=0, le=25)
    orders: list[Order] = Field(max_length=10)
    operations: list[Operation] = Field(max_length=2)
    notifications: list[NotificationEffect] = Field(max_length=18)
    events: list[EventRecord] = Field(max_length=300)


class NoNextAction(StrictModel):
    kind: Literal["NONE", "ESCALATE"]


class CheckNextAction(StrictModel):
    kind: Literal["CHECK_EXISTING_UPGRADE", "CHECK_EXISTING_NOTIFICATION"]
    operation_id: Id


NextAction = Annotated[Union[NoNextAction, CheckNextAction], Field(discriminator="kind")]


# The agent's final report, field for field the legacy ``TaskReport`` (same JSON schema, so no docstring).
class TaskReport(StrictModel):
    upgrade_outcome: Literal["NOT_STARTED", "PENDING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    notification_outcome: Literal["NOT_STARTED", "PENDING", "SUCCEEDED", "FAILED", "UNKNOWN", "NOT_REQUIRED"]
    overall: Literal["COMPLETED", "SAFE_UNRESOLVED", "CORRECTLY_REJECTED"]
    evidence_ids: list[Id] = Field(max_length=18)
    next_action: NextAction


class UpgradeRequest(StrictModel):
    order_id: Id
    desired_shipping: Literal["express"]
    expected_version: int = Field(ge=1)
    operation_id: Id
    idempotency_key: Id
    intent_hash: Digest


class NotificationRequest(StrictModel):
    order_id: Id
    upgrade_operation_id: Id
    operation_id: Id
    idempotency_key: Id
    intent_hash: Digest
    template_version: Literal["confirmation/v1"]


class F1Parameters(StrictModel):
    response_delay_ms: int = Field(ge=1500, le=3000)


class F2Parameters(StrictModel):
    completion_delay_ticks: int = Field(ge=1, le=20)
    terminal_status: Literal["SUCCEEDED", "FAILED"]
    failure_code: Literal["UPGRADE_REJECTED"] | None

    @model_validator(mode="after")
    def consistent_failure(self):
        if (self.terminal_status == "FAILED") != (self.failure_code == "UPGRADE_REJECTED"):
            raise ValueError("terminal status/failure code mismatch")
        return self


class F3Parameters(StrictModel):
    versions_back: int = Field(ge=1, le=3)


class F4Parameters(StrictModel):
    failure_count: int = Field(ge=1, le=18)


PARAMETERS = {"F1": F1Parameters, "F2": F2Parameters, "F3": F3Parameters, "F4": F4Parameters}
TOOLS_OF_KIND = {"F1": ("update_order", "send_confirmation"), "F2": ("update_order",), "F3": ("get_order",),
                 "F4": ("get_order", "update_order", "get_operation_status", "send_confirmation")}


def validate_primitive(primitive: dict) -> None:
    """The legacy fault-primitive rules: parameters per family, legal tools, tool/service agreement."""
    kind, tool, service = primitive["kind"], primitive["target_tool"], primitive["target_service"]
    if tool not in TOOLS_OF_KIND[kind] or service not in ("orders", "notifications"):
        raise ValueError("tool/kind mismatch")
    if tool != "get_operation_status" and SERVICE_OF_TOOL[tool] != service:
        raise ValueError("tool/service mismatch")
    if kind in ("F2", "F3") and service != "orders":
        raise ValueError("tool/service mismatch")
    PARAMETERS[kind].model_validate(primitive["parameters"])


__all__ = ["SCOPE", "VERSION", "CheckNextAction", "EventRecord", "F1Parameters", "F2Parameters", "F3Parameters",
           "F4Parameters", "NextAction", "NoNextAction", "NotificationEffect", "NotificationRequest", "OperationData",
           "Operation", "Order", "Receipt", "Service", "Status", "StoredStatus", "TaskIntent", "TaskReport", "Tool",
           "ToolResult", "UpgradeRequest", "WorldSnapshot", "validate_primitive"]
