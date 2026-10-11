"""What a task pack must supply to run on the kernel."""

from __future__ import annotations

from typing import Any

from faultlab.env.kernel.errors import WorldError


class WorldHandler:
    """Business semantics over the kernel. Subclass and override; the base refuses everything.

    The handler owns ``state["pack"]``; the kernel owns every other key of the world state.
    """

    pack_id: str = "unnamed-pack"
    fixtures: tuple[str, ...] = ()
    history_tables: tuple[str, ...] = ()      # append-only SQL tables the kernel protects with triggers

    def validate_intent(self, intent: dict) -> dict:
        """Return the intent as canonical JSON or raise ``WorldError(code, 422)``."""
        raise WorldError("INVALID_INTENT", 422)

    def initial_state(self, intent: dict, fixture_id: str) -> dict:
        """The pack-owned state of a fresh world; raise ``WorldError(..., 422)`` for a bad fixture."""
        raise WorldError("UNKNOWN_FIXTURE", 422)

    def validate_schedule(self, spec: dict, state: dict) -> None:
        """Refuse a fault schedule the pack cannot honour (``WorldError(..., 422)``)."""

    def histories(self, state: dict) -> dict[str, list[tuple[str, Any]]]:
        """Rows to append to each history table: ``{table: [(key, json_value), ...]}``."""
        return {}

    def before_perform(self, ctx, state: dict, tool: str, service: str, request: dict) -> float:
        """Pack hooks that run before fault placement (diagnostic fixtures); returns an added delay."""
        return 0.0

    def perform(self, ctx, state: dict, tool: str, service: str, request: dict, faults: list) -> tuple[int, dict, bool]:
        """Apply one admitted request; return ``(http_status, result_json, effect_committed)``."""
        raise WorldError("UNKNOWN_TOOL", 404)

    def error_result(self, call_id: str, tool: str, request: dict, code: str) -> dict:
        return {"call_id": call_id, "tool": tool, "transport": "error", "error_code": code}

    def on_tick(self, ctx, state: dict) -> None:
        """Complete whatever became due at the new tick."""

    def snapshot(self, state: dict):
        """The evaluator's view of the world (never shown to agents)."""
        return {"world_id": state["world_id"], "tick": state["tick"], "events": state["events"]}

    def extend_control(self, api, store) -> None:
        """Add pack-specific control routes (the router already requires the control capability)."""
