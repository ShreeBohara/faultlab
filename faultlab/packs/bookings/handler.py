"""The bookings world on the kernel: one booking, one target slot, holds and one move operation.

A port of the September pure world (``taskpacks/bookings_move_with_hold/world.py``) onto the kernel.
The kernel owns admission, ticks, budgets, the event log and the placement of F1, F4 and F5; this
handler owns the booking, the holds, the move and its idempotency, and places F2 (delayed move),
F3 (stale booking read) and F6 (short hold). The pure helpers of the September world (fixture
history, the fault grammar, the public view of a hold, deterministic ids) are reused, not copied,
so the two worlds cannot drift apart on them; the parity tests compare every answer and the final
state of both worlds on the same requests.

The rules, as in September: one tick per admitted request; at each tick a due PENDING move completes
first (failing ``HOLD_NOT_ACTIVE`` when its hold is no longer ACTIVE), then holds whose
``expires_tick`` has come expire. ``place_hold`` is not idempotent: every committed call creates a
new hold. ``move_booking`` is idempotent by the trusted operation id and key, and a move onto a hold
that is not ACTIVE is refused before acceptance. ``release_hold`` is idempotent per hold.
"""

from __future__ import annotations

import copy

from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.handler import WorldHandler
from faultlab.env.kernel.storage import event
from faultlab.packs.bookings import models as m
from taskpacks.bookings_move_with_hold import table, world as september

PACK_ID = m.SCOPE
FIXTURES = table.FIXTURES


def _mint(pack: dict, prefix: str) -> str:
    counts = pack["mint"]["counts"]
    counts[prefix] = counts.get(prefix, 0) + 1
    return september.make_id(pack["mint"]["seed"], prefix, counts[prefix])


def _hold(pack: dict, hold_id) -> dict | None:
    return next((hold for hold in pack["holds"] if hold["hold_id"] == hold_id), None)


def move_view(pack: dict, intent: dict) -> dict:
    """The one move operation as a status read shows it (the September ``_move_view``)."""
    move = pack["move"]
    if move is None:
        return {"kind": "move_operation", "operation_id": intent["move_operation_id"], "status": "UNKNOWN", "hold_id": None,
                "receipt": None}
    return {"kind": "move_operation", "operation_id": move["operation_id"], "status": move["state"], "hold_id": move["hold_id"],
            "receipt": copy.deepcopy(move["receipt"])}


def complete_move(state: dict, move: dict) -> None:
    """End a move at the current tick; the receipt is the only authority (the September ``_complete_move``)."""
    pack, intent = state["pack"], state["intent"]
    hold = _hold(pack, move["hold_id"])
    if move["terminal_status"] == "FAILED":
        status, failure = "FAILED", move["failure_code"]
    elif hold is not None and hold["state"] == "ACTIVE":
        status, failure = "SUCCEEDED", None
    else:
        status, failure = "FAILED", "HOLD_NOT_ACTIVE"
    version = None
    if status == "SUCCEEDED":
        hold["state"], hold["closed_tick"] = "CONSUMED", state["tick"]
        booking = {"booking_id": pack["booking"]["booking_id"], "slot": intent["target_slot"], "version": pack["booking"]["version"] + 1}
        pack["booking"] = booking
        pack["history"].append(dict(booking))
        version = booking["version"]
    move["state"], move["terminal_tick"] = status, state["tick"]
    move["receipt"] = {"receipt_id": _mint(pack, "receipt"), "operation_id": move["operation_id"], "hold_id": move["hold_id"],
                       "status": status, "failure_code": failure, "terminal_tick": state["tick"], "booking_version": version}
    if status == "SUCCEEDED":
        event(state, "hold_consumed", {"hold_id": hold["hold_id"], "operation_id": move["operation_id"]})
        event(state, "move_succeeded", {"operation_id": move["operation_id"], "hold_id": move["hold_id"],
                                        "receipt_id": move["receipt"]["receipt_id"], "booking_version": version})
    else:
        event(state, "move_failed", {"operation_id": move["operation_id"], "hold_id": move["hold_id"], "failure_code": failure,
                                     "receipt_id": move["receipt"]["receipt_id"]})


class BookingsHandler(WorldHandler):
    pack_id = PACK_ID
    fixtures = FIXTURES
    history_tables = ("projections", "receipts")

    def validate_intent(self, intent):
        try:
            return m.TaskIntent.model_validate(intent).model_dump(mode="json")
        except ValueError as error:
            raise WorldError("INVALID_INTENT", 422) from error

    def initial_state(self, intent, fixture_id):
        if fixture_id not in FIXTURES:
            raise WorldError("UNKNOWN_FIXTURE", 422)
        history = september.fixture_history(fixture_id, intent)
        return {"booking": dict(history[-1]), "history": history,
                "slot": {"slot_id": intent["target_slot"], "capacity": table.TARGET_CAPACITY},
                "holds": [], "move": None, "move_idempotency": None, "mint": {"seed": "world|" + intent["task_id"], "counts": {}}}

    def validate_schedule(self, spec, state):
        """The September fault grammar, on the kernel's form (which also names each fault's service)."""
        primitives = []
        for primitive in spec["primitives"]:
            if m.SERVICE_OF_TOOL.get(primitive["target_tool"]) != primitive["target_service"]:
                raise WorldError("TARGET_NOT_ALLOWED", 422)
            primitives.append({key: primitive[key] for key in ("kind", "target_tool", "occurrence", "parameters")})
        try:
            september.validate_fault_spec({"scope": PACK_ID, "primitives": primitives}, state["fixture_id"])
        except september.FaultSpecError as error:
            raise WorldError(error.code, 422) from error
        for primitive in primitives:
            if primitive["kind"] == "F3" and len(state["pack"]["history"]) <= primitive["parameters"]["versions_back"]:
                raise WorldError("STALE_HISTORY_UNAVAILABLE", 422)

    def histories(self, state):
        pack = state["pack"]
        receipts = [(pack["move"]["receipt"]["receipt_id"], pack["move"]["receipt"])] if pack["move"] and pack["move"]["receipt"] else []
        receipts += [(hold["release_receipt"]["receipt_id"], hold["release_receipt"]) for hold in pack["holds"] if hold["release_receipt"]]
        return {"projections": [(projection["version"], projection) for projection in pack["history"]], "receipts": receipts}

    def error_result(self, call_id, tool, request, code, data=None):
        return {"call_id": call_id, "tool": tool, "transport": "error", "error_code": code, "data": data}

    def on_transient_refusal(self, ctx, state, faults):
        """A 503 before any effect pre-empts every other fault aimed at the same attempt (the September rule)."""
        for index, primitive in faults:
            if primitive["kind"] not in ("F1", "F4"):
                ctx.prevented(index, "pre_effect_failure")

    def perform(self, ctx, state, tool, service, request, faults):
        try:
            status, data, committed = self._perform(ctx, state, tool, request, faults)
        except WorldError:
            # A refusal commits nothing: no answer of it can be lost or replaced, and no move was accepted.
            for index, primitive in faults:
                if primitive["kind"] in ("F1", "F5", "F6"):
                    ctx.prevented(index, "target_not_committed")
                elif primitive["kind"] == "F2":
                    ctx.prevented(index, "target_not_accepted")
            raise
        return status, {"call_id": ctx.call_id, "tool": tool, "transport": "ok", "error_code": None, "data": data}, committed

    def _perform(self, ctx, state, tool, request, faults):
        pack, intent = state["pack"], state["intent"]
        body = request.get("payload") if isinstance(request.get("payload"), dict) else request
        for source in (request, body):
            if source.get("booking_id") not in (None, intent["booking_id"]):
                raise WorldError("IDENTITY_CONFLICT")
        for key in ("hold_id", "operation_id"):                  # a route's path and its body must name the same thing
            if body is not request and request.get(key) is not None and body.get(key) != request[key]:
                raise WorldError("IDENTITY_CONFLICT")
        if tool == "get_booking":
            projection = pack["booking"]
            for index, primitive in faults:
                if primitive["kind"] == "F3":
                    projection = pack["history"][-1 - primitive["parameters"]["versions_back"]]
                    ctx.trigger(index)
            return 200, {"kind": "booking_projection", **projection}, False
        if tool == "list_holds":
            return 200, {"kind": "hold_list", "as_of_tick": state["tick"], "holds": [september.public_hold(h) for h in pack["holds"]]}, False
        if tool == "get_move_status":
            if request.get("operation_id") not in (None, intent["move_operation_id"]):
                raise WorldError("IDENTITY_CONFLICT")
            return 200, move_view(pack, intent), False
        if tool == "place_hold":
            return self._place_hold(ctx, state, body, faults)
        if tool == "move_booking":
            return self._move_booking(ctx, state, body, faults)
        if tool == "release_hold":
            return self._release_hold(ctx, state, body)
        raise WorldError("UNKNOWN_TOOL", 404)

    def _place_hold(self, ctx, state, body, faults):
        pack, intent = state["pack"], state["intent"]
        if body.get("slot_id") != intent["target_slot"]:
            raise WorldError("IDENTITY_CONFLICT")
        if sum(1 for hold in pack["holds"] if hold["state"] == "ACTIVE") >= pack["slot"]["capacity"]:
            raise WorldError("NO_CAPACITY")
        ttl = table.HOLD_TTL_TICKS
        for index, primitive in faults:
            if primitive["kind"] == "F6":
                ttl -= primitive["parameters"]["ttl_cut_ticks"]
                ctx.trigger(index)
        hold = {"hold_id": _mint(pack, "hold"), "slot": intent["target_slot"], "state": "ACTIVE", "created_tick": state["tick"],
                "expires_tick": state["tick"] + ttl, "closed_tick": None, "release_receipt": None}
        pack["holds"].append(hold)
        ctx.event("hold_created", {"hold_id": hold["hold_id"], "expires_tick": hold["expires_tick"], "attempt_id": ctx.attempt_id})
        return 201, {"kind": "hold", **september.public_hold(hold)}, True

    def _move_booking(self, ctx, state, body, faults):
        pack, intent = state["pack"], state["intent"]
        fields = {key: body.get(key) for key in ("booking_id", "hold_id", "operation_id", "idempotency_key", "intent_hash")}
        payload_hash = september.content_hash(fields)
        known = pack["move_idempotency"]
        if known is not None and known["key"] == fields["idempotency_key"]:
            if known["payload_hash"] != payload_hash:
                raise WorldError("IDEMPOTENCY_CONFLICT")
            for index, primitive in faults:
                if primitive["kind"] == "F2":
                    ctx.prevented(index, "target_not_accepted")
            return 200, move_view(pack, intent), pack["move"]["state"] == "SUCCEEDED"
        if (fields["operation_id"] != intent["move_operation_id"] or fields["idempotency_key"] != intent["move_idempotency_key"]
                or fields["intent_hash"] != intent["move_intent_hash"]):
            raise WorldError("IDENTITY_CONFLICT")
        hold = _hold(pack, fields["hold_id"])
        if hold is None:
            raise WorldError("UNKNOWN_HOLD", 404)
        if hold["state"] != "ACTIVE":
            raise WorldError("HOLD_NOT_ACTIVE", 409, data={"hold_id": hold["hold_id"], "hold_state": hold["state"]})
        move = {"operation_id": fields["operation_id"], "hold_id": hold["hold_id"], "payload_hash": payload_hash, "state": "PENDING",
                "accepted_tick": state["tick"], "due_tick": state["tick"], "terminal_status": "SUCCEEDED", "failure_code": None,
                "terminal_tick": None, "receipt": None}
        pack["move"] = move
        pack["move_idempotency"] = {"key": fields["idempotency_key"], "payload_hash": payload_hash}
        ctx.event("move_accepted", {"operation_id": move["operation_id"], "hold_id": move["hold_id"], "payload_hash": payload_hash})
        delayed = next(((index, primitive) for index, primitive in faults if primitive["kind"] == "F2"), None)
        if delayed is not None:
            index, primitive = delayed
            status = primitive["parameters"]["terminal_status"]
            move.update(due_tick=state["tick"] + primitive["parameters"]["completion_delay_ticks"], terminal_status=status,
                        failure_code="MOVE_REJECTED" if status == "FAILED" else None)
            ctx.trigger(index)
            return 202, move_view(pack, intent), False
        complete_move(state, move)
        return 200, move_view(pack, intent), True

    def _release_hold(self, ctx, state, body):
        pack = state["pack"]
        hold = _hold(pack, body.get("hold_id"))
        if hold is None:
            raise WorldError("UNKNOWN_HOLD", 404)
        if hold["state"] == "CONSUMED":
            raise WorldError("HOLD_CONSUMED", 409, data={"hold_id": hold["hold_id"], "hold_state": "CONSUMED"})
        if hold["state"] == "EXPIRED":
            return 200, {"kind": "hold_release", "hold_id": hold["hold_id"], "state": "EXPIRED", "effect": "none", "receipt": None}, False
        replay = hold["state"] == "RELEASED"
        if not replay:
            hold["state"], hold["closed_tick"] = "RELEASED", state["tick"]
            hold["release_receipt"] = {"receipt_id": _mint(pack, "release"), "hold_id": hold["hold_id"], "released_tick": state["tick"]}
            ctx.event("hold_released", {"hold_id": hold["hold_id"], "receipt_id": hold["release_receipt"]["receipt_id"]})
        return 200, {"kind": "hold_release", "hold_id": hold["hold_id"], "state": "RELEASED", "effect": "replayed" if replay else "released",
                     "receipt": copy.deepcopy(hold["release_receipt"])}, True

    def on_tick(self, ctx, state):
        pack = state["pack"]
        move = pack["move"]
        if move is not None and move["state"] == "PENDING" and move["due_tick"] <= state["tick"]:
            complete_move(state, move)
        for hold in pack["holds"]:
            if hold["state"] == "ACTIVE" and hold["expires_tick"] <= state["tick"]:
                hold["state"], hold["closed_tick"] = "EXPIRED", state["tick"]
                event(state, "hold_expired", {"hold_id": hold["hold_id"]})

    def snapshot(self, state):
        """The evaluator's private view (the September ``snapshot`` plus the world id). Never shown to an agent."""
        pack = state["pack"]
        return copy.deepcopy({"world_id": state["world_id"], "task_definition_id": PACK_ID, "tick": state["tick"],
                              "stopped": state["stopped"], "decision_tick": state.get("decision_tick"), "attempts": state["attempts"],
                              "waits": state["waits"], "booking": pack["booking"], "history": pack["history"], "holds": pack["holds"],
                              "move": pack["move"], "events": state["events"], "fault_executions": state["fault_executions"]})


__all__ = ["BookingsHandler", "FIXTURES", "PACK_ID", "complete_move", "move_view"]
