"""The bookings pack's public data: the trial's intent, the agent's report and the services of its tools.

The task, the tool table, the fault grammar and the report shape are the September pack's own
(``taskpacks/bookings_move_with_hold/table.py``, the one table that pack declares once). This
module turns them into the strict models the v2 lab validates against; it adds no rule of its own.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from faultlab.core.model import StrictModel
from taskpacks.bookings_move_with_hold import table

SCOPE = table.TASK_DEFINITION_ID
VERSION = "1"
Ident = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SERVICE_OF_TOOL = {name: spec["service"] for name, spec in table.TOOLS.items()}


class TaskIntent(StrictModel):
    """The trusted identities of one trial. The agent never chooses any of them."""
    task_id: Ident
    booking_id: Ident
    original_slot: Ident
    target_slot: Ident
    move_operation_id: Ident
    move_idempotency_key: Ident
    move_intent_hash: Hash
    task_text: Annotated[str, StringConstraints(min_length=1, max_length=600)]


class NoAction(StrictModel):
    kind: Literal["NONE", "ESCALATE"]


class CheckExistingMove(StrictModel):
    kind: Literal["CHECK_EXISTING_MOVE"]
    operation_id: Ref


class ReleaseHold(StrictModel):
    kind: Literal["RELEASE_HOLD"]
    hold_id: Ref


class MoveReport(StrictModel):
    """The agent's final report (the September ``MoveReport``): shape only; truth is the referee's question."""
    move_outcome: Literal["NOT_STARTED", "PENDING", "SUCCEEDED", "FAILED", "UNKNOWN"]
    booking_slot: Literal["ORIGINAL", "TARGET", "UNKNOWN"]
    open_hold_ids: list[Ref] = Field(max_length=table.REPORT["max_open_hold_ids"])
    overall: Literal["COMPLETED", "SAFE_UNRESOLVED", "CORRECTLY_REJECTED"]
    evidence_ids: list[Ref] = Field(max_length=table.REPORT["max_evidence_ids"])
    next_action: NoAction | CheckExistingMove | ReleaseHold = Field(discriminator="kind")

    @model_validator(mode="after")
    def _no_duplicates(self):
        for name in ("open_hold_ids", "evidence_ids"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} has duplicates")
        return self


__all__ = ["CheckExistingMove", "MoveReport", "NoAction", "ReleaseHold", "SCOPE", "SERVICE_OF_TOOL", "TaskIntent", "VERSION"]
