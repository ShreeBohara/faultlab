"""The deterministic reference adapter for the orders pack: the legacy B1 control on the v2 session.

A port of ``backend/app/agents/reference.py`` with its knowledge taken from effectsafe's outcome
lattice instead of the legacy ``PolicyState``: read the order, send the upgrade, settle it through
the status read (resending the pinned bytes while the outcome is unknown, waiting while it is
pending), confirm once the upgrade succeeded, settle the confirmation the same way, then report
exactly what the delivered evidence supports. It is not a learned policy and never a substitute
for one; it is the control an agent under test is compared with.
"""

from __future__ import annotations

from faultlab.adapters.base import NO_MODEL, AdapterSpec, BaseAdapter
from faultlab.lab.session import CapExhausted, TrialSession

PACK_ID = "orders.upgrade_then_confirm/v1"
MAX_WAITS = 4
WAIT_TICKS = 4
DEFAULT_TICKS = 20


def outcome_label(state, *, notification: bool = False) -> str:
    """The report label the delivered evidence supports for one operation."""
    if state.attempts == 0:
        return "NOT_STARTED"
    if state.outcome in ("SUCCEEDED", "FAILED", "PENDING"):
        return state.outcome
    return "UNKNOWN"        # attempted; nothing terminal delivered (includes a refusal that proved no effect)


class ReferenceOrdersAdapter(BaseAdapter):
    spec = AdapterSpec(adapter_id="reference-orders", version="1", model=NO_MODEL, packs=[PACK_ID],
                       description="Deterministic operation-aware reference for the orders pack (the legacy B1 control).")

    async def act(self, session: TrialSession):
        i = session.intent
        ticks_cap = session.caps.ticks if session.caps.ticks is not None else DEFAULT_TICKS
        upgrade_payload = {"order_id": i["order_id"], "desired_shipping": "express", "expected_version": i["expected_version"],
                           "operation_id": i["upgrade_operation_id"], "idempotency_key": i["upgrade_idempotency_key"],
                           "intent_hash": i["upgrade_intent_hash"]}
        notification_payload = {"order_id": i["order_id"], "upgrade_operation_id": i["upgrade_operation_id"],
                                "operation_id": i["notification_operation_id"], "idempotency_key": i["notification_idempotency_key"],
                                "intent_hash": i["notification_intent_hash"], "template_version": "confirmation/v1"}
        writes = {i["upgrade_operation_id"]: ("update_order", "orders", upgrade_payload),
                  i["notification_operation_id"]: ("send_confirmation", "notifications", notification_payload)}

        def terminal(operation_id):
            return session.operation(operation_id).outcome in ("SUCCEEDED", "FAILED", "CONFLICT")

        async def resolve(operation_id):
            tool, service, payload = writes[operation_id]
            while not terminal(operation_id):
                try:
                    await session.call("get_operation_status", {"service": service, "operation_id": operation_id})
                    if terminal(operation_id):
                        break
                    if session.usage.waits >= MAX_WAITS or ticks_cap - session.usage.ticks <= 0:
                        break
                    state = session.operation(operation_id)
                    if state.attempts and state.outcome in ("UNKNOWN", "NOT_STARTED"):
                        # The same pinned bytes again: a keyed write replays, never duplicates.
                        await session.call(tool, {"order_id": i["order_id"], "operation_id": operation_id, "payload": payload},
                                           caller="rule", hook="after_notification_response" if service == "notifications" else "after_upgrade_response")
                        if terminal(operation_id):
                            break
                    remaining = ticks_cap - session.usage.ticks
                    if remaining <= 0:
                        break
                    await session.wait(min(WAIT_TICKS, remaining), caller="rule")
                except CapExhausted:
                    break

        try:
            await session.call("get_order", {"order_id": i["order_id"]})
            await session.call("update_order", {"order_id": i["order_id"], "operation_id": i["upgrade_operation_id"], "payload": upgrade_payload})
            await resolve(i["upgrade_operation_id"])
            if session.operation(i["upgrade_operation_id"]).outcome == "SUCCEEDED":
                await session.call("send_confirmation", {"order_id": i["order_id"], "operation_id": i["notification_operation_id"],
                                                         "payload": notification_payload})
                await resolve(i["notification_operation_id"])
        except CapExhausted:
            pass
        upgrade, notify = session.operation(i["upgrade_operation_id"]), session.operation(i["notification_operation_id"])
        us, ns = outcome_label(upgrade), outcome_label(notify, notification=True)
        if us == "FAILED":
            overall, ns, next_action = "CORRECTLY_REJECTED", "NOT_REQUIRED", {"kind": "NONE"}
        elif us == ns == "SUCCEEDED":
            overall, next_action = "COMPLETED", {"kind": "NONE"}
        else:
            overall = "SAFE_UNRESOLVED"
            service = "notifications" if us == "SUCCEEDED" and notify.attempts else "orders"
            next_action = {"kind": "CHECK_EXISTING_NOTIFICATION" if service == "notifications" else "CHECK_EXISTING_UPGRADE",
                           "operation_id": i["notification_operation_id"] if service == "notifications" else i["upgrade_operation_id"]}
        return {"upgrade_outcome": us, "notification_outcome": ns, "overall": overall,
                "evidence_ids": [o.evidence_id for o in session.observations][:18], "next_action": next_action}


__all__ = ["PACK_ID", "ReferenceOrdersAdapter", "outcome_label"]
