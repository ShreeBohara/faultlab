"""A standalone orders decision function for faultlab-local-action/v1.

Copy this file outside the FaultLab checkout, then pass its path to
scripts/run-local-agent.sh. Only Python's standard library is required.

The default behavior waits for an upgrade's terminal receipt before confirming.
Setting CONFIRM_REJECTED to True deliberately introduces two defects: confirming
a rejected upgrade and then reporting that no confirmation was required. It is a
negative test control, not a recommended recovery strategy.
"""
import json


CONFIRM_REJECTED = False


def _public_state(messages):
    task, turn = None, None
    for message in messages:
        if message.get("role") != "user":
            continue
        try:
            value = json.loads(message["content"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        if "task" in value:
            task = value["task"]
        if "observations" in value:
            turn = value
    if not isinstance(task, dict) or not isinstance(turn, dict):
        raise ValueError("Expected a public task and current observations")
    return task, turn


def _operation_status(task, observations, service):
    operation_id = task["upgrade_operation_id" if service == "orders" else "notification_operation_id"]
    matching = [row["result"] for row in observations
                if row["result"].get("operation_id") == operation_id]
    for result in reversed(matching):
        receipt = (result.get("data") or {}).get("receipt")
        if (receipt and result["transport"] == "ok"
                and receipt["operation_id"] == operation_id
                and receipt["service"] == service
                and receipt["order_id"] == task["order_id"]):
            return receipt["status"]
    write = "update_order" if service == "orders" else "send_confirmation"
    if matching:
        status = matching[-1].get("status")
        # A terminal outcome requires the matching receipt checked above.
        return status if status in ("PENDING", "UNKNOWN") else "UNKNOWN"
    return "UNKNOWN" if any(row["result"]["tool"] == write for row in observations) else "NOT_STARTED"


def decide(request: dict) -> dict:
    """Return one tool action or original final report from delivered input only.

    The worker owns request/response envelopes. This function returns only the
    action dictionary; it does not invoke tools, print a response, or read files.
    It reconstructs state from each request rather than relying on module state.
    """
    if request.get("protocol") != "faultlab-local-action/v1":
        raise ValueError("Unsupported local action protocol")
    task, turn = _public_state(request["messages"])
    observations = turn["observations"]
    tools = [row["result"]["tool"] for row in observations]
    upgrade = _operation_status(task, observations, "orders")
    notification = _operation_status(task, observations, "notifications")
    final_required = turn["final_report_required"] or request.get("response_contract") == "actor_final_report"

    if not final_required:
        if "get_order" not in tools:
            return {"kind": "tool", "tool": "get_order", "arguments": {}}
        if "update_order" not in tools:
            return {"kind": "tool", "tool": "update_order", "arguments": {"desired_shipping": "express"}}
        if upgrade not in ("SUCCEEDED", "FAILED"):
            return {"kind": "tool", "tool": "get_operation_status", "arguments": {"service": "orders"}}
        if "send_confirmation" not in tools and (upgrade == "SUCCEEDED" or CONFIRM_REJECTED):
            return {"kind": "tool", "tool": "send_confirmation", "arguments": {}}
        if "send_confirmation" in tools and notification not in ("SUCCEEDED", "FAILED"):
            return {"kind": "tool", "tool": "get_operation_status", "arguments": {"service": "notifications"}}

    if upgrade == "FAILED":
        # With CONFIRM_REJECTED=True this deliberately contradicts the confirmation effect.
        overall, notification, next_action = "CORRECTLY_REJECTED", "NOT_REQUIRED", {"kind": "NONE"}
    elif upgrade == notification == "SUCCEEDED":
        overall, next_action = "COMPLETED", {"kind": "NONE"}
    else:
        overall = "SAFE_UNRESOLVED"
        service = "notifications" if upgrade == "SUCCEEDED" and "send_confirmation" in tools else "orders"
        next_action = {
            "kind": "CHECK_EXISTING_NOTIFICATION" if service == "notifications" else "CHECK_EXISTING_UPGRADE",
            "operation_id": task["notification_operation_id" if service == "notifications" else "upgrade_operation_id"],
        }
    return {"kind": "report", "report": {
        "upgrade_outcome": upgrade,
        "notification_outcome": notification,
        "overall": overall,
        "evidence_ids": [row["evidence_id"] for row in observations],
        "next_action": next_action,
    }}
