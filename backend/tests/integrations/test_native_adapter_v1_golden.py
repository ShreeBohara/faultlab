"""Golden pin: native adapter v1 (smolagents-toolcalling-v1) keeps its exact model-visible bytes.

Adapter v2 (app.integrations.external_agent_v2) reuses v1's code by import. This test pins what v1
sends to the model, byte for byte, for fixed scripted episodes, so a change made for v2 (or anywhere
in the shared code: smolagents, the TaskReport schema, canonical JSON, the provider layer) cannot
silently change v1. It also pins v1's native_prompt_hash.

The fixture backend/tests/fixtures/native_v1_golden_requests.json was captured from the unchanged
v1 code before adapter v2 existed (September 29, 2026). Identifiers are made deterministic by
replacing uuid4 in app.contracts.models (every new_id() of the lab and simulator goes through it).
Real smolagents 1.26.0, real in-process simulator, scripted model transport; no provider call.

To regenerate deliberately (never to make a failure pass): FAULTLAB_WRITE_NATIVE_GOLDEN=1 pytest this file.
"""
import asyncio
import itertools
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.contracts.models import canonical_json, content_hash
from app.providers.runtime import RuntimeGeneration

from test_agent_contract import native_context

MODEL = "openai/gpt-oss-120b"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "native_v1_golden_requests.json"
# v1's prompt identity (registry.native_prompt_hash), unchanged since the native probe.
V1_NATIVE_PROMPT_HASH = "2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989"


def deterministic_ids(monkeypatch):
    """Every new_id() (lab journal, broker, simulator) and every smolagents tool-call id draws from a counter."""
    import uuid
    import app.contracts.models as models
    from app.integrations.external_agent import _import_smolagents
    _import_smolagents()   # the adapter's own guarded import (no implicit .env load)
    import smolagents.models
    counter, calls = itertools.count(1), itertools.count(1)
    monkeypatch.setattr(models, "uuid4", lambda: SimpleNamespace(hex=f"{next(counter):032x}"))
    monkeypatch.setattr(smolagents.models, "uuid", SimpleNamespace(uuid4=lambda: uuid.UUID(int=next(calls))))


class Recorder:
    """Scripted model transport that records every request exactly as it was handed over."""
    def __init__(self, script):
        self.script, self.requests = script, []

    async def complete(self, messages, **kwargs):
        self.requests.append({"messages": messages, "kwargs": dict(sorted(kwargs.items()))})
        output = self.script(len(self.requests), messages)
        return RuntimeGeneration(output if isinstance(output, str) else json.dumps(output), MODEL, 100, 20)


def report_citing(ids, *, outcome="SUCCEEDED"):
    return {"name": "final_answer", "arguments": {"answer": {
        "upgrade_outcome": outcome, "notification_outcome": outcome, "overall": "COMPLETED",
        "evidence_ids": ids, "next_action": {"kind": "NONE"}}}}


def success_script(call, messages):
    """Read, upgrade, confirm, then report citing the evidence_id strings the agent was shown."""
    if call == 1: return {"name": "get_order", "arguments": {}}
    if call == 2: return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
    if call == 3: return {"name": "send_confirmation", "arguments": {}}
    return report_citing(shown_evidence_ids(messages))


def no_report_script(call, messages):
    """Poll forever with one invalid output at call 3; the eighth request is the flagged final turn."""
    if call == 3: return "not a tool call"
    return {"name": "get_operation_status", "arguments": {"service": "orders"}}


def embedded_objects(messages):
    """Every JSON object in a request, including JSON embedded in native memory text ('Observation: {...}')."""
    found = []
    def walk(value):
        if isinstance(value, dict):
            found.append(value)
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
        elif isinstance(value, str):
            decoder, cursor = json.JSONDecoder(), 0
            while (index := value.find("{", cursor)) >= 0:
                try: child, used = decoder.raw_decode(value[index:])
                except ValueError: cursor = index + 1; continue
                walk(child); cursor = index + used
    walk(messages)
    return found


def shown_evidence_ids(messages):
    """The evidence_id strings of the observations the agent was shown, in first-seen order (what a model can cite)."""
    seen = []
    for row in embedded_objects(messages):
        if isinstance(row.get("result"), dict) and isinstance(row.get("evidence_id"), str) and row["evidence_id"] not in seen:
            seen.append(row["evidence_id"])
    return seen


SCRIPTS = {"success": success_script, "no_report": no_report_script}


async def run_episode(tmp_path, store, baseline, actor_class, script, episode_id):
    """Run one scripted native episode; return (requests, outcome, context)."""
    provider = Recorder(script)
    intent, context, client = await native_context(tmp_path, store, baseline, provider, episode_id)
    try:
        try:
            report = await actor_class(model_id=MODEL)(intent, context)
            outcome = {"report": report.model_dump(mode="json")}
        except Exception as error:
            outcome = {"error": type(error).__name__, "message": str(error)}
    finally:
        await client.close()
    return provider.requests, outcome, context


def capture(tmp_path, store, baseline, monkeypatch, actor_class, name):
    deterministic_ids(monkeypatch)
    return asyncio.run(run_episode(tmp_path, store, baseline, actor_class, SCRIPTS[name], f"golden-{name}"))


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_v1_request_bytes_are_pinned(tmp_path, store, baseline, monkeypatch, name):
    from app.integrations.external_agent import SmolagentsActor
    requests, outcome, _ = capture(tmp_path, store, baseline, monkeypatch, SmolagentsActor, name)
    observed = {"requests": requests, "outcome": outcome,
                "request_bytes_sha256": [content_hash(r["messages"]) for r in requests]}
    golden = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}
    if os.environ.get("FAULTLAB_WRITE_NATIVE_GOLDEN") == "1":
        golden[name] = observed
        FIXTURE.write_text(json.dumps(golden, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        pytest.skip("golden fixture written; rerun without FAULTLAB_WRITE_NATIVE_GOLDEN")
    assert name in golden, "missing golden fixture; see the module docstring"
    # Exact bytes: every message of every request, in order, and the provider keyword arguments.
    assert [canonical_json(r["messages"]) for r in requests] == [canonical_json(r["messages"]) for r in golden[name]["requests"]]
    assert [r["kwargs"] for r in requests] == [r["kwargs"] for r in golden[name]["requests"]]
    assert observed["request_bytes_sha256"] == golden[name]["request_bytes_sha256"]
    assert outcome == golden[name]["outcome"]
    # v1 never asks the provider for a response contract (structured output is v2 only).
    assert all("response_contract" not in r["kwargs"] for r in requests)


def test_v1_native_prompt_hash_is_pinned():
    from app.integrations.registry import native_prompt_hash
    assert native_prompt_hash() == V1_NATIVE_PROMPT_HASH


def test_golden_episodes_cover_the_final_turn_and_the_refused_fallback():
    golden = json.loads(FIXTURE.read_text())
    flags = [json.loads(r["messages"][-1]["content"])["final_report_required"] for r in golden["no_report"]["requests"]]
    assert flags == [False] * 7 + [True]                       # eight requests; only the eighth is the final turn
    assert golden["no_report"]["outcome"]["error"] == "ActorReportError"   # the ninth (fallback) was never sent
    tools = [t["name"] for t in json.loads(golden["no_report"]["requests"][-1]["messages"][-1]["content"])["tools"]]
    assert tools == ["get_order", "update_order", "get_operation_status", "send_confirmation", "final_answer"]
    assert golden["success"]["outcome"]["report"]["overall"] == "COMPLETED"
