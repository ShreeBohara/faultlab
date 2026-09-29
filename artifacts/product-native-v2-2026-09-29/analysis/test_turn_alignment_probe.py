"""$0 offline probe: how FaultLab's actor meter lines up with smolagents max_steps=8.

Runs the real native adapter (app.integrations.external_agent.SmolagentsActor, unchanged) and the
installed smolagents 1.26.0 against an in-process simulator (httpx ASGI transport, no sockets)
with a scripted fake provider. No model, provider, W&B or Weave call is made.

Run from backend/ so the repository's own offline guards (tests/conftest.py: network refusal,
.env audit hook, scratch simulator import) are loaded as a plugin:

  cd faultlab/backend && PYTHONPATH=tests PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest \
      -q -c pytest.ini --rootdir . -p conftest -p no:cacheprovider \
      ../artifacts/product-native-v2-2026-09-29/analysis/test_turn_alignment_probe.py

Results are written to turn_alignment_probe.out.json beside this file.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.business_tools import BusinessToolBroker, WorldClient
from app.adapters.journal import Journal, allocate_intent
from app.agents.actor import ActorReportError
from app.config import Settings
from app.contracts.models import FaultSpec, TaskReport, canonical_json
from app.integrations.external_agent import SmolagentsActor, _import_smolagents
from app.lab.budgets import EpisodeMeter
from app.lab.policies import PolicyRepository
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app

MODEL = "openai/gpt-oss-120b"
OUT = Path(__file__).with_name("turn_alignment_probe.out.json")
RESULTS = {}


async def native_context(tmp_path, store, baseline, provider, episode_id):
    # Same construction as backend/tests/integrations/test_agent_contract.py::native_context
    app = create_app(database_dir=tmp_path / episode_id, control_token="offline-control", settings=Settings())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8001")
    world_client = WorldClient("http://127.0.0.1:8001", "offline-control", client=client)
    intent = allocate_intent("order-1", "Upgrade this order to express and send its confirmation.")
    world = await world_client.create(episode_id, intent, FaultSpec(seed=42, primitives=[]))
    store.put_record("episodes", episode_id, {"campaign_id": "offline-native"})
    journal = Journal(store, episode_id, intent)
    broker = BusinessToolBroker(world_client, world["world_id"], world["capability"], journal, EpisodeMeter())
    interpreter = PolicyInterpreter(baseline.content, broker)
    context = SimpleNamespace(provenance=SimpleNamespace(episode_id=episode_id, origin="prototype"), provider=provider,
                              broker=broker, interpreter=interpreter, metadata={"model_id": MODEL}, lab_mode=True,
                              adapter_id="orders/v1", policy=baseline.content, policy_hash=baseline.policy_hash,
                              policy_decision=baseline.decision, trace=None)
    return intent, context, world_client


class ScriptedProvider:
    """Returns the scripted output for each call and records what the model was told."""
    def __init__(self, script, context_ref):
        self.script, self.context_ref, self.seen = script, context_ref, []

    async def complete(self, messages, **kwargs):
        last = json.loads(messages[-1]["content"])
        self.seen.append({"call": len(self.seen) + 1, "final_report_required": last.get("final_report_required"),
                          "remaining_actor_calls": last.get("remaining_actor_calls")})
        output = self.script(len(self.seen), self.context_ref[0])
        return RuntimeGeneration(output if isinstance(output, str) else json.dumps(output), MODEL, 100, 20)


def report(context, mangle=False):
    ids = [o.evidence_id for o in context.broker.journal.observations]
    if mangle and ids:
        ids[0] = ids[0][:17] + "极" + ids[0][18:]   # the stray token seen live: '极' replaces one hex char
    return {"name": "final_answer", "arguments": {"answer": {
        "upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
        "evidence_ids": ids, "next_action": {"kind": "NONE"}}}}


BUSINESS = [{"name": "get_order", "arguments": {}},
            {"name": "update_order", "arguments": {"desired_shipping": "express"}},
            {"name": "send_confirmation", "arguments": {}}]


def business(call):
    return BUSINESS[call - 1] if call <= 3 else {"name": "get_operation_status", "arguments": {"service": "orders"}}


SCENARIOS = {
    # C: turns 1-8 are business calls; turn 8 is refused ("Final report required")
    "C_business_call_on_turn_8": lambda call, ctx: business(call),
    # A: first report attempt only on turn 8, with one corrupted evidence ID
    "A_corrupted_id_on_turn_8": lambda call, ctx: business(call) if call < 8 else report(ctx, mangle=True),
    # A then recovery: corrupted report on turn 7, clean report on turn 8
    "A_on_turn_7_then_clean_report_on_turn_8": lambda call, ctx: (business(call) if call < 7
                                                                   else report(ctx, mangle=(call == 7))),
    # D: turn 8 output is a fenced JSON block (not exactly one JSON object)
    "D_invalid_action_on_turn_8": lambda call, ctx: (business(call) if call < 8
                                                     else "```json\n" + json.dumps(report(ctx)) + "\n```"),
    # control: clean report on turn 4
    "clean_report_on_turn_4": lambda call, ctx: business(call) if call < 4 else report(ctx),
}


@pytest.fixture(scope="module", autouse=True)
def write_results():
    yield
    OUT.write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_turn_alignment(name, tmp_path, monkeypatch):
    _import_smolagents()
    import smolagents.agents as sa
    fallback = []
    original = sa.MultiStepAgent.provide_final_answer

    def spy(self, task):
        message = original(self, task)
        content = message.content
        text = content if isinstance(content, str) else " ".join(p.get("text", "") for p in content)
        fallback.append({"called": True, "returned_text_prefix": text[:120]})
        return message

    monkeypatch.setattr(sa.MultiStepAgent, "provide_final_answer", spy)
    store = LabStore(":memory:")
    baseline = PolicyRepository(store).baseline()

    async def run():
        ref = [None]
        provider = ScriptedProvider(SCENARIOS[name], ref)
        intent, context, client = await native_context(tmp_path, store, baseline, provider, f"probe-{name[:20]}")
        ref[0] = context
        outcome = {}
        try:
            result = await SmolagentsActor(model_id=MODEL)(intent, context)
            outcome = {"result": "REPORT", "overall": result.overall}
        except ActorReportError as error:
            outcome = {"result": "ActorReportError", "message": str(error)}
        except Exception as error:  # recorded, then asserted below
            outcome = {"result": type(error).__name__, "message": str(error)[:200]}
        usage = context.broker.meter.usage
        RESULTS[name] = {"provider_calls": len(provider.seen), "what_the_model_was_told": provider.seen,
                         "meter_actor_calls": usage.actor_calls, "meter_model_calls": usage.model_calls,
                         "dispatched_business_calls": len(context.broker.logical_calls),
                         "smolagents_provide_final_answer": fallback or [{"called": False}], **outcome}
        await client.close()

    asyncio.run(run())
    got = RESULTS[name]
    # The meter's final turn is smolagents' step 8, and the model is told so on that call only.
    assert got["provider_calls"] <= 8 and got["meter_model_calls"] == got["provider_calls"]
    flags = [s["final_report_required"] for s in got["what_the_model_was_told"]]
    assert flags == [False] * (len(flags) - 1) + [len(flags) == 8] if len(flags) == 8 else not any(flags)
    if name == "clean_report_on_turn_4" or name.startswith("A_on_turn_7"):
        assert got["result"] == "REPORT"
    else:
        assert got["provider_calls"] == 8 and got["result"] == "ActorReportError"
        # smolagents' max-steps fallback ran but its 9th generation was refused by the meter
        assert got["smolagents_provide_final_answer"][0]["called"]
        assert "Actor budget exhausted" in got["smolagents_provide_final_answer"][0]["returned_text_prefix"]


def test_fallback_text_could_not_validate_even_if_sent():
    """smolagents returns the fallback's text as a string; the adapter validates
    canonical_json(result), i.e. a JSON string literal, which can never be a TaskReport."""
    perfect = json.dumps({"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                          "evidence_ids": ["evidence-1"], "next_action": {"kind": "NONE"}})
    TaskReport.model_validate_json(perfect)          # the text itself is a valid report ...
    with pytest.raises(ValueError):
        TaskReport.model_validate_json(canonical_json(perfect))   # ... but not once wrapped as a string
    RESULTS["fallback_string_validation"] = {"valid_report_text_as_string_result": "rejected by TaskReport"}
