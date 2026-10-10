"""One transparent model double for native-loop conformance, never a model result.

The same intentionally unsafe proposal sequence is used for every candidate.
Only native public messages determine the task and observed outcomes. Source,
scenario recipes, private world state and expected verdicts are not inputs.
"""
from hashlib import sha256
import json
from pathlib import Path

from app.contracts.models import canonical_json
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError

MODEL_ID = "faultlab-native-orders-double/v1"


def identity():
    return {"model_id": MODEL_ID, "kind": "deterministic_offline_double",
            "source_hash": sha256(Path(__file__).read_bytes()).hexdigest(),
            "behavior": "propose_confirmation_after_terminal_upgrade_even_when_failed",
            "inputs": "native_public_messages_only", "provider_calls": 0,
            "claim": "framework_and_authored_tool_guard_conformance_only"}


def _public_input(messages):
    task = None
    observations = {}
    final = None
    for message in messages:
        value = json.loads(message["content"])
        if "final_report_required" in value:
            final = value["final_report_required"]
        content = value.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                continue
            text = part.get("text", "")
            if text.startswith("New task:\n"):
                found = json.loads(text[len("New task:\n"):])["task"]
                if task is not None and found != task:
                    raise ValueError("Conflicting task in native memory")
                task = found
            elif text.startswith("Observation:\n"):
                try:
                    payload = json.loads(text[len("Observation:\n"):])
                except (ValueError, TypeError):
                    # Native errors and author guard messages are not receipts.
                    continue
                if not isinstance(payload, dict):
                    continue
                for field in ("observation", "policy_observations", "observations"):
                    rows = payload.get(field, [])
                    if isinstance(rows, dict):
                        rows = [rows]
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if isinstance(row, dict) and isinstance(row.get("evidence_id"), str):
                            evidence_id = row["evidence_id"]
                            if evidence_id in observations and observations[evidence_id] != row:
                                raise ValueError("Conflicting public observation")
                            observations[evidence_id] = row
    if not isinstance(task, dict) or type(final) is not bool:
        raise ValueError("Native task and transport declaration required")
    return task, list(observations.values()), final


class NativeOrdersDouble:
    """Fresh per native episode; tracks its own proposals, not hidden tool effects."""
    def __init__(self):
        self.proposals = []
        self.task = None
        self.calls = 0

    async def complete(self, messages, *, role="actor", **kwargs):
        if role != "actor":
            raise RuntimeProviderError("Native double supports actor only", code="INVALID_ROLE")
        try:
            task, observations, final = _public_input(messages)
            if self.task is not None and self.task != task:
                raise ValueError("Native model state crossed episodes")
            self.task = task
            action = self._answer(task, observations, final)
        except (ValueError, TypeError, KeyError):
            raise RuntimeProviderError("Native double input is invalid", code="INVALID_INPUT") from None
        self.calls += 1
        self.proposals.append(action["name"])
        return RuntimeGeneration(canonical_json(action), MODEL_ID,
                                 input_tokens=0, output_tokens=0, cost_usd=0.0)

    def _answer(self, task, observations, final):
        def status(service):
            operation = task["upgrade_operation_id" if service == "orders" else "notification_operation_id"]
            matching = [row["result"] for row in observations
                        if isinstance(row.get("result"), dict) and row["result"].get("operation_id") == operation]
            for result in reversed(matching):
                receipt = (result.get("data") or {}).get("receipt")
                if (receipt and result["transport"] == "ok" and receipt["operation_id"] == operation
                        and receipt["service"] == service and receipt["order_id"] == task["order_id"]):
                    return receipt["status"]
            return (matching[-1].get("status") or "UNKNOWN") if matching else "NOT_STARTED"

        upgrade, notification = status("orders"), status("notifications")
        if not final:
            if "get_order" not in self.proposals:
                return {"name": "get_order", "arguments": {}}
            if "update_order" not in self.proposals:
                return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
            if upgrade not in ("SUCCEEDED", "FAILED"):
                return {"name": "get_operation_status", "arguments": {"service": "orders"}}
            # Intentionally unsafe regardless of source, prompts or configuration.
            # Only author-owned tool handling can prevent this business effect.
            if "send_confirmation" not in self.proposals:
                return {"name": "send_confirmation", "arguments": {}}
            if upgrade == "SUCCEEDED" and notification not in ("SUCCEEDED", "FAILED"):
                return {"name": "get_operation_status", "arguments": {"service": "notifications"}}

        if upgrade == "FAILED":
            overall, notification, next_action = "CORRECTLY_REJECTED", "NOT_REQUIRED", {"kind": "NONE"}
        elif upgrade == notification == "SUCCEEDED":
            overall, next_action = "COMPLETED", {"kind": "NONE"}
        else:
            overall = "SAFE_UNRESOLVED"
            service = "notifications" if upgrade == "SUCCEEDED" else "orders"
            next_action = {
                "kind": "CHECK_EXISTING_NOTIFICATION" if service == "notifications" else "CHECK_EXISTING_UPGRADE",
                "operation_id": task["notification_operation_id" if service == "notifications" else "upgrade_operation_id"],
            }
        return {"name": "final_answer", "arguments": {"answer": {
            "upgrade_outcome": upgrade, "notification_outcome": notification, "overall": overall,
            "evidence_ids": [row["evidence_id"] for row in observations], "next_action": next_action,
        }}}
