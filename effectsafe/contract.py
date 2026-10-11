"""What a connector promises about a tool (architecture section 4.1); shared with the lab's packs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1, max_length=120)
    kind: Literal["read", "write"]
    # How the provider recognises "the same operation": nothing (every call is a new effect), a
    # client-supplied key, a natural key in the payload, or a server-side task the client polls.
    identity_scope: Literal["none", "client_key", "natural_key", "server_task"] = "none"
    key_placement: Literal["header", "field", "directive", "natural"] | None = None
    key_retention_seconds: int | None = Field(default=None, ge=0)
    # What a replay with the same key does: replay the first result, conflict, create anew, or unknown.
    mismatch_behavior: Literal["replay", "conflict", "new_effect", "unknown"] = "unknown"
    commit_boundary: Literal["on_ack", "async", "unknown"] = "unknown"
    status_lookup: str | None = None             # the read that returns the operation's state, if any
    pending_states: frozenset[str] = frozenset({"PENDING"})
    terminal_states: frozenset[str] = frozenset({"SUCCEEDED", "FAILED"})
    errors_proving_no_effect: frozenset[str] = frozenset()   # e.g. a 400 validation before admission
    retry_safe_errors: frozenset[str] = frozenset()          # only meaningful when identity_scope != none

    @property
    def resend_is_identity_safe(self) -> bool:
        """A same-bytes resend cannot create a second effect only when the provider keys the operation."""
        return self.kind == "write" and self.identity_scope in ("client_key", "natural_key", "server_task") \
            and self.mismatch_behavior in ("replay", "conflict")
