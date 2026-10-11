"""The outcome lattice and reconciliation (architecture section 8.3).

Per operation: ``NOT_STARTED`` until a dispatch is journalled; ``UNKNOWN`` from the moment bytes
may have reached the provider until evidence settles it; ``PENDING`` when an acceptance was
delivered; ``SUCCEEDED`` or ``FAILED`` with a terminal receipt; ``CONFLICT`` when two terminal
receipts disagree. Two rules are never broken: ``UNKNOWN`` and ``PENDING`` never decay back to
``NOT_STARTED``, and a terminal state never reverts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NOT_STARTED, UNKNOWN, PENDING, SUCCEEDED, FAILED, CONFLICT = "NOT_STARTED", "UNKNOWN", "PENDING", "SUCCEEDED", "FAILED", "CONFLICT"
Outcome = Literal["NOT_STARTED", "UNKNOWN", "PENDING", "SUCCEEDED", "FAILED", "CONFLICT"]
RANK = {NOT_STARTED: 0, UNKNOWN: 1, PENDING: 2, SUCCEEDED: 3, FAILED: 3, CONFLICT: 4}


class Evidence(BaseModel):
    """What one attempt delivered, in the provider's terms."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    transport: Literal["ok", "timeout", "error"]
    status: str | None = None                      # the provider's state word, if any
    receipt_id: str | None = None                  # a terminal receipt's identity, if delivered
    error_code: str | None = None
    proves_no_effect: bool = False                 # the contract says this error happens before admission


class OperationState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    outcome: Outcome = NOT_STARTED
    attempts: int = Field(default=0, ge=0)        # dispatches journalled
    in_flight: int = Field(default=0, ge=0)       # dispatched, nothing delivered yet
    unresolved: int = Field(default=0, ge=0)      # delivered, but the attempt's effect is still unknown
    receipt_id: str | None = None
    last_status: str | None = None
    history: list[str] = Field(default_factory=list, max_length=256)

    @property
    def effect_possibly_pending(self) -> bool:
        """True while any attempt may have taken effect without evidence saying so."""
        return self.in_flight > 0 or self.unresolved > 0 or self.outcome in (UNKNOWN, PENDING)


def reconcile(state: OperationState, evidence: Evidence, *, terminal_states: frozenset[str] = frozenset({"SUCCEEDED", "FAILED"}),
              pending_states: frozenset[str] = frozenset({"PENDING"})) -> OperationState:
    """Fold one attempt's evidence into the operation's outcome; monotonic on the lattice."""
    if state.outcome == CONFLICT:
        state.history.append(f"ignored:{evidence.transport}:{evidence.status}")
        return state
    if evidence.transport != "ok":
        # Lost reply or transport error: nothing is known about this attempt's effect.
        state.unresolved += 1
        if RANK[state.outcome] < RANK[UNKNOWN]:
            state.outcome = UNKNOWN
        state.history.append(f"{evidence.transport}:{evidence.error_code or ''}")
        return state
    if evidence.status in terminal_states:
        terminal = SUCCEEDED if evidence.status == "SUCCEEDED" else FAILED
        if state.outcome in (SUCCEEDED, FAILED) and state.outcome != terminal:
            state.outcome = CONFLICT
            state.history.append(f"conflict:{terminal}:{evidence.receipt_id}")
            return state
        if state.receipt_id and evidence.receipt_id and state.receipt_id != evidence.receipt_id:
            state.outcome = CONFLICT
            state.history.append(f"conflict:receipt:{evidence.receipt_id}")
            return state
        state.outcome = terminal
        state.receipt_id = evidence.receipt_id or state.receipt_id
        state.last_status = evidence.status
        state.unresolved = 0
        state.history.append(f"terminal:{terminal}")
        return state
    if evidence.status in pending_states:
        if RANK[state.outcome] < RANK[PENDING]:
            state.outcome = PENDING
        state.last_status = evidence.status
        state.history.append("pending")
        return state
    if evidence.proves_no_effect:
        # This attempt provably did nothing. If no other attempt is in doubt, the operation is back
        # to not started; otherwise its standing is whatever the earlier attempts left.
        state.history.append(f"no_effect:{evidence.error_code or ''}")
        if state.outcome == UNKNOWN and state.in_flight == 0 and state.unresolved == 0:
            state.outcome = NOT_STARTED
        return state
    # An acknowledged but uninformative reply (an error after admission, an unknown status word).
    state.unresolved += 1
    if RANK[state.outcome] < RANK[UNKNOWN]:
        state.outcome = UNKNOWN
    state.last_status = evidence.status
    state.history.append(f"unsettled:{evidence.status or evidence.error_code or ''}")
    return state
