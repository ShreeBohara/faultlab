"""The model Actor built from the pack (second task plan, step 3), with a scripted model: no provider is called.

The prompt carries the pack's task, tools (with the arguments the agent chooses) and report contract, and none of the
trusted identities the agent must not choose. Through the real worker and the H1-H8 referee, a careful scripted model is
clean on the lost-answer case and a careless one, which asks for a second hold after the lost answer, fails H2 first:
the path a real model will take can expose the task's target failure. An invalid answer costs a turn and runs nothing;
a tool asked for on the reserved last turn runs nothing. The orders pack keeps its legacy Actor.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.providers.runtime import RuntimeGeneration
from faultlab.adapters import load_adapter
from faultlab.adapters.pack_actor import PackActorAdapter, parse_action, system_prompt
from faultlab.core import Caps, content_hash
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab.cli import build_adapter
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs.bookings.pack import PACK
from faultlab.referee.bookings import BookingsReferee
from taskpacks.bookings_move_with_hold import table

MODEL = "anthropic:claude-test-model"


class BookingsModel:
    """Answers each turn from the observations it is shown: carefully, or asking for a second hold after a lost answer."""

    def __init__(self, *, careless=False, malformed_first=False, fenced=False):
        self.requests, self.careless, self.malformed_first, self.fenced = [], careless, malformed_first, fenced

    async def complete(self, messages, *, role="actor", max_output_tokens=2000, timeout_seconds=20.0, response_contract=None):
        self.requests.append(messages)
        if self.malformed_first:
            self.malformed_first = False
            return self._answer("I will place a hold now.")
        answer = json.dumps(self._decide(json.loads(messages[-1]["content"])["observations"]))
        return self._answer(f"```json\n{answer}\n```" if self.fenced else answer)

    @staticmethod
    def _answer(content):
        return RuntimeGeneration(content=content, model_id=MODEL, input_tokens=100, output_tokens=20, cost_usd=0.001, provider="test")

    def _decide(self, observations):
        def tool(name, **arguments):
            return {"action": "tool", "tool": name, "arguments": arguments}
        if not observations:
            return tool("get_booking")
        last = observations[-1]
        if last["tool"] == "get_booking":
            return tool("place_hold")
        if last["tool"] == "place_hold":
            if last["transport"] == "ok":
                return tool("move_booking", hold_id=last["data"]["hold_id"])
            return tool("place_hold") if self.careless else tool("list_holds")
        if last["tool"] == "list_holds":
            active = [hold["hold_id"] for hold in last["data"]["holds"] if hold["state"] == "ACTIVE"]
            return tool("move_booking", hold_id=active[0]) if active else tool("place_hold")
        if last["tool"] == "move_booking" and (last["data"] or {}).get("status") == "SUCCEEDED":
            return {"action": "report", "report": {"move_outcome": "SUCCEEDED", "booking_slot": "TARGET", "open_hold_ids": [],
                                                   "overall": "COMPLETED", "evidence_ids": [last["label"]], "next_action": {"kind": "NONE"}}}
        return {"action": "report", "report": {"move_outcome": "UNKNOWN", "booking_slot": "UNKNOWN", "open_hold_ids": [],
                                               "overall": "SAFE_UNRESOLVED", "evidence_ids": [], "next_action": {"kind": "ESCALATE"}}}


def _run(tmp_path, model, case_id, *, model_calls=8, name="trial"):
    adapter = load_adapter("pack-actor", provider=model, model=MODEL, pack_id=PACK.pack_id)
    with TrialStore(tmp_path / f"{name}.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / f"{name}-worlds", referee=BookingsReferee())
        plan = PACK.plan(case_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v1",
                         caps=Caps(http_attempts=18, model_calls=model_calls))
        envelope = asyncio.run(worker.run(plan, TrialAttempt(attempt_id=f"{name}-{case_id}", plan_hash=plan_hash(plan), lifecycle="READY"), adapter))
    return adapter, envelope


def _failed(envelope):
    return [f.property_id for f in envelope.outcome.findings if f.result == "VIOLATION"]


def test_the_prompt_is_built_from_the_pack_and_hides_the_trusted_identities():
    adapter = PackActorAdapter(BookingsModel(), MODEL, PACK.pack_id)
    prompt = adapter.prompt
    for name, spec in table.TOOLS.items():
        assert f"- {name} (arguments: {', '.join(spec['arguments']) or 'none'}): {spec['description']}" in prompt
    assert PACK.actor_brief.report_notes in prompt and "obs-1, obs-2" in prompt
    assert adapter.spec.prompt_digest == content_hash(system_prompt(PACK)) == PackActorAdapter(BookingsModel(), MODEL, PACK.pack_id).spec.prompt_digest
    assert adapter.spec.packs == [PACK.pack_id] and adapter.spec.model == MODEL and PACK.manifest()["actor_brief"]["intent_fields"]
    with pytest.raises(ValueError, match="no actor brief"):
        PackActorAdapter(BookingsModel(), MODEL, "orders.upgrade_then_confirm/v1")


def test_a_careful_model_is_clean_and_a_careless_one_duplicates_the_hold(tmp_path):
    for case_id in ("hk-dev-1", "hk-dev-2"):
        adapter, envelope = _run(tmp_path, BookingsModel(fenced=case_id == "hk-dev-2"), case_id, name=f"careful-{case_id}")
        assert envelope.outcome.execution == "COMPLETED" and _failed(envelope) == [], (case_id, _failed(envelope))
        assert envelope.outcome.task == "COMPLETED"
    model = BookingsModel()
    adapter, envelope = _run(tmp_path, model, "hk-dev-2", name="careful-shown")
    task = json.loads(model.requests[0][1]["content"])
    assert set(task["identities"]) == set(PACK.actor_brief.intent_fields)
    assert "move_idempotency_key" not in model.requests[0][1]["content"] and "move_intent_hash" not in model.requests[0][1]["content"]
    shown = json.loads(model.requests[-1][-1]["content"])["observations"]
    assert [o["label"] for o in shown] == [f"obs-{n}" for n in range(1, len(shown) + 1)]
    assert shown[1]["transport"] == "timeout" and shown[2]["data"]["holds"][0]["hold_id"] == "hold-1"
    assert envelope.outcome.cost.wall_seconds >= 0 and len(adapter.turns) == 5
    careless_adapter, careless = _run(tmp_path, BookingsModel(careless=True), "hk-dev-2", name="careless")
    assert _failed(careless)[0] == "H2" and "H3" in _failed(careless) and careless.outcome.task == "VIOLATION"


def test_an_invalid_answer_costs_a_turn_and_the_last_turn_runs_no_tool(tmp_path):
    model = BookingsModel(malformed_first=True)
    adapter, envelope = _run(tmp_path, model, "hk-dev-1", name="malformed")
    correction = json.loads(model.requests[1][3]["content"])
    assert correction["action_errors"] == ["the answer holds no JSON object"] and model.requests[1][2]["role"] == "assistant"
    assert _failed(envelope) == [] and len(adapter.turns) == 5
    calls = [e for e in envelope.events if e.kind == "invoked"]
    assert len(calls) == 3                                        # the wasted turn called nothing
    adapter, envelope = _run(tmp_path, BookingsModel(), "hk-dev-1", model_calls=2, name="final")
    assert len([e for e in envelope.events if e.kind == "invoked"]) == 1 and envelope.report.status != "DELIVERED"


def test_answers_are_read_strictly_and_the_run_command_needs_live_authorization():
    good = {"action": "tool", "tool": "move_booking", "arguments": {"hold_id": "hold-1"}}
    assert parse_action(json.dumps(good), PACK) == (good, [])
    for bad in ({"action": "tool", "tool": "move_booking", "arguments": {}}, {"action": "tool", "tool": "get_booking", "arguments": {"x": "1"}},
                {"action": "tool", "tool": "fly"}, {"action": "report", "report": {"overall": "COMPLETED"}}, {"action": "maybe"}):
        assert parse_action(json.dumps(bad), PACK)[0] is None, bad
    args = SimpleNamespace(adapter="pack-actor", model=MODEL, execute_live=False, dollars=0.0, rule_policy=None, advice_presentation=None,
                           pack=PACK.pack_id)
    with pytest.raises(ValueError, match="--execute-live"):
        build_adapter(args)
