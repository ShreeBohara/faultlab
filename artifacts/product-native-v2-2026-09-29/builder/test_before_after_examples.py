"""$0 offline: capture what the agent sees under adapter v1 and v2 for the same scripted episodes (fake, counter IDs).

Real smolagents, in-process simulator, scripted transport; no provider call. Run from faultlab/backend:
  PYTHONPATH=tests/integrations ../.venv/bin/python -m pytest -q -p no:cacheprovider \
      ../artifacts/product-native-v2-2026-09-29/builder/test_before_after_examples.py
Writes before_after_examples.json beside this file.
"""
import json
from pathlib import Path

from app.integrations.external_agent import SmolagentsActor
from app.integrations.external_agent_v2 import SmolagentsActorV2
from test_native_adapter_v2 import SCRIPTS, episode

OUT = Path(__file__).with_name("before_after_examples.json")


def tool_result(request):
    """The newest tool-result message (smolagents memory text 'Observation: {...}')."""
    for message in reversed(request["messages"]):
        content = json.loads(message["content"]).get("content")
        text = content[0]["text"] if isinstance(content, list) and content else ""
        if text.startswith("Observation:"):
            return text
    return None


def test_capture(tmp_path, monkeypatch):
    out = {}
    for label, actor in (("v1", SmolagentsActor), ("v2", SmolagentsActorV2)):
        success, _, success_context, _ = episode(tmp_path / f"{label}-s", actor, SCRIPTS["success"], name="example-success", monkeypatch=monkeypatch)
        polls, outcome, _, _ = episode(tmp_path / f"{label}-n", actor, SCRIPTS["no_report"], name="example-no-report", monkeypatch=monkeypatch)
        final = polls.requests[-1]
        out[label] = {
            "second_request_newest_tool_result": tool_result(success.requests[1]),
            "stored_evidence_ids": [o.evidence_id for o in success_context.broker.journal.observations],
            "final_turn_request_last_message": json.loads(final["messages"][-1]["content"]),
            "final_turn_provider_arguments": final["kwargs"],
            "requests_in_no_report_episode": len(polls.requests),
            "no_report_outcome": outcome,
        }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
