"""How the September broker presented evidence, rebuilt from a v2 session's records (bookings pack).

The September agents and checks read observations labelled ``obs-1``, ``obs-2``, ... that carry the actor
turn, the tick and the HTTP attempts used at delivery. The v2 session records the same deliveries and the
calls that made them. ``september_observations`` turns those records into the September form in delivery
order, so the agent's view (hold labels as the agent saw them) and the referee's input (the world's ids put
back) come from one function and cannot disagree on numbering. A local refusal (a call with no HTTP attempt)
is the September ``refused`` delivery. The turn of a call is its position among the agent's calls: a
September agent makes exactly one call or one report per turn.
"""

from __future__ import annotations

import copy


def swap_references(value, key: str, mapping: dict):
    """``value`` with every string under ``key`` replaced through ``mapping`` (unknown strings kept)."""
    if isinstance(value, dict):
        return {k: mapping.get(v, v) if k == key and isinstance(v, str) else swap_references(v, key, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [swap_references(item, key, mapping) for item in value]
    return value


def september_observations(observations: list[dict], calls: list[dict], *, real_of: dict | None = None, key: str = "hold_id") -> list[dict]:
    turn_of, caller_of, attempts_after, local = {}, {}, {}, set()
    turn = used = 0
    for call in calls:
        agent = (call.get("caller") or "agent") in ("agent", "replay")
        turn += 1 if agent else 0
        turn_of[call["call_id"]] = turn
        caller_of[call["call_id"]] = "actor" if agent else call.get("caller")
        if not call.get("attempt_ids"):
            local.add(call["call_id"])
        for attempt in call.get("attempt_ids") or []:
            used += 1
            attempts_after[attempt] = used
    out, used = [], 0
    for number, item in enumerate(observations, 1):
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        refused = item["call_id"] in local
        used = attempts_after.get(item.get("attempt_id"), used)
        status = item.get("http_status")
        if refused:
            transport = "refused"
        elif item.get("transport") == "timeout":
            transport = "timeout"
        else:
            transport = "ok" if isinstance(status, int) and 200 <= status < 300 else "error"
        data = copy.deepcopy(result.get("data"))
        if real_of:
            data = swap_references(data, key, real_of)
        out.append({"label": f"obs-{number}", "turn": turn_of.get(item["call_id"], turn), "tick": item["delivered_tick"],
                    "http_attempts_used": used, "tool": item["tool"], "caller": caller_of.get(item["call_id"], "actor"),
                    "call_id": item["call_id"], "attempt_id": None if refused else item.get("attempt_id"), "transport": transport,
                    "http_status": None if refused else status, "error_code": result.get("error_code"), "data": data})
    return out


__all__ = ["september_observations", "swap_references"]
