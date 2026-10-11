"""The orders world on the kernel: four tools with transaction-before-response semantics.

A faithful port of ``backend/app/simulator/{business,clock}.py`` and the fixture rules of its
``storage.py``, with the kernel owning admission, ticks, budgets, F1/F4 placement and the
event log, and this handler owning orders, operations, idempotency and notifications.
"""

from __future__ import annotations

from faultlab.core.canonical import content_hash
from faultlab.core.ids import new_id
from faultlab.env.kernel.errors import WorldError
from faultlab.env.kernel.handler import WorldHandler
from faultlab.env.kernel.storage import event
from faultlab.packs.orders import models as m

PACK_ID = m.SCOPE
FIXTURE_VERSIONS = {"standard-v1": 1, "history-v1": 4}


def operation_result(call_id, tool, op, intent) -> dict:
    receipt = m.Receipt.model_validate(op["receipt"]) if op["receipt"] else None
    data = m.OperationData(operation_id=op["operation_id"], service=op["service"], order_id=op["order_id"],
                           intent_hash=op["intent_hash"], status=op["state"], receipt=receipt)
    return m.ToolResult(call_id=call_id, tool=tool, transport="ok", operation_id=op["operation_id"], order_id=op["order_id"],
                        status=op["state"], observed_version=op["receipt"].get("committed_version") if op["receipt"] else None,
                        receipt_id=op["receipt"]["receipt_id"] if op["receipt"] else None,
                        retry_after_ticks=1 if op["state"] == "PENDING" else None, data=data).model_dump(mode="json")


def complete_upgrade(state, op) -> None:
    """Commit or fail a pending upgrade at the current tick; the receipt is the only authority."""
    if op["state"] != "PENDING":
        return
    pack = state["pack"]
    failed = op.get("failure_code")
    if not failed and pack["order"]["version"] != op["expected_version"]:
        failed = "VERSION_CONFLICT"
    status = "FAILED" if failed else "SUCCEEDED"
    version = None
    if not failed:
        pack["order"] = {**pack["order"], "applied_shipping": op["desired_shipping"], "requested_shipping": op["desired_shipping"],
                         "version": pack["order"]["version"] + 1, "last_upgrade_operation_id": op["operation_id"]}
        pack["history"].append(dict(pack["order"]))
        version = pack["order"]["version"]
    else:
        pack["order"]["requested_shipping"] = pack["order"]["applied_shipping"]
    op["state"] = status
    op["terminal_tick"] = state["tick"]
    op["receipt"] = m.Receipt(receipt_id=new_id("receipt"), operation_id=op["operation_id"], service="orders",
                              order_id=op["order_id"], intent_hash=op["intent_hash"], status=status, terminal_tick=state["tick"],
                              committed_version=version, failure_code=failed).model_dump(mode="json")
    event(state, "upgrade_committed" if not failed else "upgrade_failed",
          {"operation_id": op["operation_id"], "order_id": op["order_id"], "receipt_id": op["receipt"]["receipt_id"], "version": version})


class OrdersHandler(WorldHandler):
    pack_id = PACK_ID
    fixtures = tuple(FIXTURE_VERSIONS)
    history_tables = ("projections", "receipts")

    def validate_intent(self, intent):
        try:
            return m.TaskIntent.model_validate(intent).model_dump(mode="json")
        except ValueError as error:
            raise WorldError("INVALID_INTENT", 422) from error

    def initial_state(self, intent, fixture_id):
        initial_version = FIXTURE_VERSIONS[fixture_id]
        if intent["expected_version"] != initial_version:
            raise WorldError("FIXTURE_VERSION_MISMATCH", 422)
        history = [m.Order(order_id=intent["order_id"], applied_shipping="standard", requested_shipping="standard", version=v)
                   .model_dump(mode="json") for v in range(1, initial_version + 1)]
        return {"order": history[-1], "history": history, "operations": {}, "idempotency": {}, "notifications": [],
                "diagnostic": None}

    def validate_schedule(self, spec, state):
        for primitive in spec["primitives"]:
            try:
                m.validate_primitive(primitive)
            except ValueError as error:
                raise WorldError("INVALID_FAULT_SPEC", 422) from error
            if primitive["kind"] == "F3" and len(state["pack"]["history"]) <= primitive["parameters"]["versions_back"]:
                raise WorldError("STALE_HISTORY_UNAVAILABLE", 422)

    def histories(self, state):
        pack = state["pack"]
        return {"projections": [(projection["version"], projection) for projection in pack["history"]],
                "receipts": [(op["receipt"]["receipt_id"], op["receipt"]) for op in pack["operations"].values() if op.get("receipt")]}

    def before_perform(self, ctx, state, tool, service, request):
        from faultlab.packs.orders.diagnostics import before_perform
        return before_perform(self, ctx, state, tool, service, request)

    def error_result(self, call_id, tool, request, code):
        return m.ToolResult(call_id=call_id, tool=tool, transport="error", operation_id=request.get("operation_id"),
                            order_id=request.get("order_id"), error_code=code).model_dump(mode="json")

    def perform(self, ctx, state, tool, service, request, faults):
        pack, intent = state["pack"], state["intent"]
        order_id, operation_id, payload = request.get("order_id"), request.get("operation_id"), request.get("payload")
        oid = intent["upgrade_operation_id" if service == "orders" else "notification_operation_id"]
        expected_hash = intent["upgrade_intent_hash" if service == "orders" else "notification_intent_hash"]
        if order_id is not None and order_id != intent["order_id"] or operation_id is not None and operation_id != oid:
            raise WorldError("IDENTITY_CONFLICT")
        if tool == "get_order":
            projection = pack["order"]
            for index, primitive in faults:
                if primitive["kind"] == "F3":
                    projection = pack["history"][-1 - primitive["parameters"]["versions_back"]]
                    ctx.trigger(index)
            return 200, m.ToolResult(call_id=ctx.call_id, tool=tool, transport="ok", order_id=order_id,
                                     observed_version=projection["version"], data=projection).model_dump(mode="json"), False
        if tool == "get_operation_status":
            op = pack["operations"].get(oid)
            if op:
                return 200, operation_result(ctx.call_id, tool, op, intent), False
            data = m.OperationData(operation_id=oid, service=service, order_id=intent["order_id"], intent_hash=expected_hash, status="UNKNOWN")
            return 200, m.ToolResult(call_id=ctx.call_id, tool=tool, transport="ok", operation_id=oid, order_id=intent["order_id"],
                                     status="UNKNOWN", data=data).model_dump(mode="json"), False
        body = dict(payload)
        payload_hash = content_hash(body)
        key = service + ":" + body["idempotency_key"]
        existing = pack["idempotency"].get(key)
        # Identity-safe same-byte replay must precede the expected-version precondition.
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise WorldError("IDEMPOTENCY_CONFLICT")
            op = pack["operations"][existing["operation_id"]]
            return 200, operation_result(ctx.call_id, tool, op, intent), op["state"] == "SUCCEEDED"
        expected_key = intent["upgrade_idempotency_key" if service == "orders" else "notification_idempotency_key"]
        if (body["operation_id"] != oid or body["order_id"] != intent["order_id"] or body["intent_hash"] != expected_hash
                or body["idempotency_key"] != expected_key):
            raise WorldError("IDENTITY_CONFLICT")
        if oid in pack["operations"]:
            raise WorldError("IDENTITY_CONFLICT")
        if tool == "update_order" and body["expected_version"] != pack["order"]["version"]:
            raise WorldError("VERSION_CONFLICT")
        if tool == "send_confirmation" and (body["upgrade_operation_id"] != intent["upgrade_operation_id"]
                                            or body["template_version"] != intent["template_version"]):
            raise WorldError("IDENTITY_CONFLICT")
        op = dict(schema_version=m.VERSION, operation_id=oid, service=service, task_id=intent["task_id"], order_id=intent["order_id"],
                  payload_hash=payload_hash, state="PENDING", accepted_tick=state["tick"], terminal_tick=None, receipt=None,
                  intent_hash=expected_hash)
        pack["operations"][oid] = op
        pack["idempotency"][key] = {"payload_hash": payload_hash, "operation_id": oid}
        ctx.event("operation_accepted", {"operation_id": oid, "service": service, "payload_hash": payload_hash})
        if tool == "update_order":
            op.update(expected_version=body["expected_version"], desired_shipping=body["desired_shipping"], failure_code=None)
            pack["order"]["requested_shipping"] = "express"
            delayed = next(((index, primitive) for index, primitive in faults if primitive["kind"] == "F2"), None)
            if delayed:
                index, primitive = delayed
                op.update(due_tick=state["tick"] + primitive["parameters"]["completion_delay_ticks"],
                          failure_code=primitive["parameters"]["failure_code"])
                ctx.trigger(index)
                return 202, operation_result(ctx.call_id, tool, op, intent), False
            complete_upgrade(state, op)
            return 200, operation_result(ctx.call_id, tool, op, intent), True
        effect = m.NotificationEffect(notification_id=new_id("notification"), order_id=intent["order_id"],
                                      upgrade_operation_id=intent["upgrade_operation_id"], operation_id=oid,
                                      idempotency_key=body["idempotency_key"], payload_hash=payload_hash, created_tick=state["tick"])
        pack["notifications"].append(effect.model_dump(mode="json"))
        op.update(state="SUCCEEDED", terminal_tick=state["tick"],
                  receipt=m.Receipt(receipt_id=new_id("receipt"), operation_id=oid, service=service, order_id=intent["order_id"],
                                    intent_hash=expected_hash, status="SUCCEEDED", terminal_tick=state["tick"],
                                    effect_id=effect.notification_id).model_dump(mode="json"))
        ctx.event("notification_committed", {"operation_id": oid, "upgrade_operation_id": intent["upgrade_operation_id"],
                                             "order_id": intent["order_id"], "effect_id": effect.notification_id})
        return 201, operation_result(ctx.call_id, tool, op, intent), True

    def on_tick(self, ctx, state):
        operations = state["pack"]["operations"].values()
        for op in sorted(operations, key=lambda value: (value.get("due_tick", 26), value["accepted_tick"], value["operation_id"])):
            if op["service"] == "orders" and op["state"] == "PENDING" and op.get("due_tick", 26) <= state["tick"]:
                complete_upgrade(state, op)

    def snapshot(self, state):
        pack = state["pack"]
        hidden = ("expected_version", "intent_hash", "desired_shipping", "failure_code", "due_tick")
        operations = [{key: value for key, value in op.items() if key not in hidden} for op in pack["operations"].values()]
        return m.WorldSnapshot.model_validate({"world_id": state["world_id"], "tick": state["tick"], "orders": [pack["order"]],
                                               "operations": operations, "notifications": pack["notifications"],
                                               "events": state["events"]})

    def extend_control(self, api, store):
        from faultlab.packs.orders.diagnostics import extend_control
        extend_control(api, store)
