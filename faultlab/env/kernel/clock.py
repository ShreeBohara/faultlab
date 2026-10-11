"""Logical time advances only at admitted requests and explicit bounded waits."""

from faultlab.env.kernel.errors import WorldError


def advance(state: dict, ticks: int, *, handler, limits, ctx=None, observer: bool = False) -> None:
    if observer:
        if not state["stopped"] or state["horizon_done"] or ticks != limits.horizon_ticks:
            raise WorldError("INVALID_OBSERVER_ADVANCE")
        if state["tick"] + ticks > limits.max_tick:
            raise WorldError("TICK_BUDGET", 429)
    else:
        if state["stopped"]:
            raise WorldError("WORLD_STOPPED")
        if state["tick"] + ticks > limits.ticks:
            raise WorldError("TICK_BUDGET", 429)
    for _ in range(ticks):
        state["tick"] += 1
        handler.on_tick(ctx, state)
    if observer:
        state["horizon_done"] = True
