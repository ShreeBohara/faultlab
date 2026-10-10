"""A user-owned smolagents constructor for the synthetic orders task.

Copy this file outside the checkout and select it explicitly. The caller supplies
the model and public tools; this file supplies the native agent and its guard.
The offline model double is deliberately unsafe after a rejected upgrade.
Set PROTECT_CONFIRMATION=False only to reproduce that negative control.
"""
import json

from smolagents import Tool, ToolCallingAgent


PROTECT_CONFIRMATION = True


def build_agent(model, tools):
    """Build a fresh native agent without calling a model or tool here."""
    supplied = {tool.name: tool for tool in tools}
    expected = {"get_order", "update_order", "get_operation_status", "send_confirmation", "final_answer"}
    if len(supplied) != len(tools) or set(supplied) != expected:
        raise ValueError("Expected the five supplied orders tools")
    # This closure is new for each episode. It contains only delivered public data.
    upgrade = {"operation_id": None, "order_id": None, "intent_hash": None, "status": None}

    def observe(text, expected_tool):
        try:
            payload = json.loads(text)
            result = payload["observation"]["result"]
            if result.get("tool") != expected_tool:
                return
            operation_id, order_id = result.get("operation_id"), result.get("order_id")
            if not all(isinstance(value, str) and value for value in (operation_id, order_id)):
                return
            if expected_tool == "update_order":
                upgrade.update(operation_id=operation_id, order_id=order_id)
            if (operation_id, order_id) != (upgrade["operation_id"], upgrade["order_id"]):
                return
            data = result.get("data")
            if result.get("transport") != "ok" or not isinstance(data, dict):
                return
            intent_hash = data.get("intent_hash")
            if (data.get("service") != "orders" or data.get("operation_id") != operation_id
                    or data.get("order_id") != order_id or not isinstance(intent_hash, str) or not intent_hash):
                return
            if upgrade["intent_hash"] not in (None, intent_hash):
                return
            upgrade["intent_hash"] = intent_hash
            receipt = data.get("receipt")
            if not isinstance(receipt, dict) or receipt.get("status") not in ("SUCCEEDED", "FAILED"):
                return
            if (receipt.get("service") != "orders" or receipt.get("operation_id") != operation_id
                    or receipt.get("order_id") != order_id or receipt.get("intent_hash") != intent_hash
                    or receipt.get("status") != data.get("status")
                    or receipt.get("status") != result.get("status")
                    or not isinstance(receipt.get("receipt_id"), str) or not receipt["receipt_id"]
                    or receipt["receipt_id"] != result.get("receipt_id")):
                return
            upgrade["status"] = receipt["status"]
        except (KeyError, TypeError, ValueError, AttributeError):
            # An absent or malformed receipt never grants permission to confirm.
            return

    original_update = supplied["update_order"]
    original_status = supplied["get_operation_status"]
    original_confirmation = supplied["send_confirmation"]

    class ObservedUpdate(Tool):
        name = original_update.name
        description = original_update.description
        inputs = original_update.inputs
        output_type = original_update.output_type

        def forward(self, desired_shipping: str):
            # A new write attempt cannot inherit a previous permission to confirm.
            upgrade.update(operation_id=None, order_id=None, intent_hash=None, status=None)
            result = original_update(desired_shipping=desired_shipping)
            observe(result, self.name)
            return result

    class ObservedStatus(Tool):
        name = original_status.name
        description = original_status.description
        inputs = original_status.inputs
        output_type = original_status.output_type

        def forward(self, service: str):
            result = original_status(service=service)
            if service == "orders":
                observe(result, self.name)
            return result

    class GuardedConfirmation(Tool):
        name = original_confirmation.name
        description = original_confirmation.description
        inputs = original_confirmation.inputs
        output_type = original_confirmation.output_type

        def forward(self):
            if PROTECT_CONFIRMATION and upgrade["status"] != "SUCCEEDED":
                # This is local guard output, not a service observation or receipt.
                # Do not manufacture an evidence ID for it.
                return json.dumps({"confirmation_blocked": True,
                                   "reason": "A matching successful upgrade receipt is required."})
            return original_confirmation()

    selected_tools = [supplied["get_order"], ObservedUpdate(), ObservedStatus(),
                      GuardedConfirmation(), supplied["final_answer"]]
    return ToolCallingAgent(model=model, tools=selected_tools, max_steps=8,
                            planning_interval=None, max_tool_threads=1,
                            verbosity_level=0, stream_outputs=False)
