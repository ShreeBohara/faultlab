"""The bookings pack on the v2 lab (second task plan, step 1).

* The declaration equals the September pack: cases, tools, hooks, checks, task text, checker digest.
* World parity: every request the September broker sent to its world, for the correct agent and the eight
  buggy agents (two of them the probe callers) on all eight cases and three seeds, gets the same answer from
  the kernel world (status, error, data, a lost answer), and both worlds end in the same state with the
  same business events, in process and over HTTP.
* The kernel's two new fault families (F5, F6), refusal bodies, and the September rule that a 503 before
  any effect pre-empts the other faults of that attempt; the orders world refuses F5 and F6.
* The session never resends a write that is not safe to repeat after an answer that does not prove it had
  no effect (a lost ``place_hold`` answer once ended the trial ``UNSAFE_RESEND_REFUSED``).

Nothing here reads the September checks: the checker digest is computed from its bytes.
"""

import asyncio
from hashlib import sha256
import json
from pathlib import Path

import pytest

from effectsafe import Journal
from faultlab.core import Caps
from faultlab.env.kernel import KernelLimits, WorldError, WorldStore, dispatch
from faultlab.evidence import AgentManifest, EnvSpec
from faultlab.lab.session import TrialSession
from faultlab.lab.transport import KernelTransport
from faultlab.packs import load_pack
from faultlab.packs.bookings import models as m
from faultlab.packs.bookings.pack import PACK, PROPERTIES, SCENARIOS
from faultlab.packs.orders.pack import PACK as ORDERS
from taskpacks.bookings_move_with_hold import driver, mutants, reference, table, world as september

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "taskpacks/bookings_move_with_hold/cases/development.json").read_text())["cases"]
AGENT = AgentManifest(adapter_id="adapter-test", model="model-test")
ENV = EnvSpec(kind="simulator")


# -- the declaration --------------------------------------------------------------------------------------

def test_the_pack_is_registered_and_equals_the_september_declaration():
    assert load_pack("bookings.move_with_hold/v1") is PACK
    assert [tool.name for tool in PACK.tools] == ["get_booking", "list_holds", "get_move_status", "place_hold", "move_booking",
                                                  "release_hold"]
    assert {tool.name for tool in PACK.tools} == set(table.TOOL_NAMES)
    assert set(PACK.read_tools) == set(table.READ_TOOLS) and set(PACK.write_tools) == set(table.WRITE_TOOLS)
    assert PACK.hooks == tuple(table.HOOKS) and PACK.fixtures == table.FIXTURES
    assert PACK.tool("place_hold").identity_scope == "none" and not PACK.tool("place_hold").resend_is_identity_safe
    assert PACK.tool("move_booking").resend_is_identity_safe and PACK.tool("release_hold").resend_is_identity_safe
    assert PACK.example_intent("standard-v1")["task_text"] == table.TASK_TEXT


def test_the_scenarios_are_the_public_cases_case_for_case():
    assert len(SCENARIOS) == len(CASES) == 8
    for scenario, case in zip(SCENARIOS, CASES):
        assert (scenario.scenario_id, scenario.label, scenario.fixture_id, scenario.fault_spec.seed, scenario.expected_class) == (
            case["case_id"], case["name"], case["fixture_id"], case["seed"], case["expected_class"])
        primitives = [{key: value for key, value in p.model_dump(mode="json").items() if key != "target_service"}
                      for p in scenario.fault_spec.primitives]
        assert primitives == case["fault_spec"]["primitives"]
        assert all(p.target_service == m.SERVICE_OF_TOOL[p.target_tool] for p in scenario.fault_spec.primitives)


def test_the_properties_are_h1_to_h8_pinned_to_the_checker_bytes():
    assert PROPERTIES.ids == list(table.CHECK_IDS)
    for spec in PROPERTIES.properties:
        name, description = table.CHECKS[spec.property_id]
        assert spec.title == f"{name}: {description}"
    assert {spec.property_id: spec.family for spec in PROPERTIES.properties}["H3"] == "abandoned_effect"
    checker = ROOT / PROPERTIES.checker_path
    assert sha256(checker.read_bytes()).hexdigest() == PROPERTIES.checker_digest


def test_the_report_model_accepts_what_the_september_shape_rules_accept():
    good = {"move_outcome": "SUCCEEDED", "booking_slot": "TARGET", "open_hold_ids": [], "overall": "COMPLETED",
            "evidence_ids": ["obs-1", "obs-4"], "next_action": {"kind": "NONE"}}
    variants = [good, {**good, "next_action": {"kind": "RELEASE_HOLD", "hold_id": "hold-1"}, "open_hold_ids": ["hold-1"]},
                {**good, "next_action": {"kind": "CHECK_EXISTING_MOVE", "operation_id": "moveop-1"}},
                {**good, "open_hold_ids": ["a", "a"]}, {**good, "next_action": {"kind": "RELEASE_HOLD"}},
                {**good, "overall": "DONE"}, {**good, "extra": 1}, {**good, "evidence_ids": [f"obs-{n}" for n in range(19)]}]
    for report in variants:
        try:
            m.MoveReport.model_validate(report)
            accepted = True
        except ValueError:
            accepted = False
        assert accepted == (table.report_problem(report) is None), report


def test_intents_are_namespaced_and_accepted_by_the_world(tmp_path):
    first, second = PACK.allocate_intent("standard-v1", "trial-1"), PACK.allocate_intent("standard-v1", "trial-2")
    assert first == PACK.allocate_intent("standard-v1", "trial-1")
    assert not (set(first.values()) - {table.TASK_TEXT}) & set(second.values())
    with pytest.raises(ValueError):
        PACK.allocate_intent("no-such-fixture", "x")


# -- world parity with the September world ----------------------------------------------------------------

def _agents():
    agents = {"reference": reference.ReferenceAgent}
    for name, factory in mutants.MUTANTS.items():
        agents[name] = factory
    return agents


def _september_run(agent_factory, case, seed_text, monkeypatch):
    """One September episode; returns its intent, every request its broker sent the world (with the answer) and its states."""
    sent = []
    original = september.handle

    def recording(state, tool, request, ctx):
        new_state, answer, events = original(state, tool, request, ctx)
        sent.append({"tool": tool, "request": json.loads(json.dumps(request)), "ctx": dict(ctx), "answer": answer})
        return new_state, answer, events

    monkeypatch.setattr(september, "handle", recording)
    record = driver.run_episode(agent_factory(), case, seed_text)
    monkeypatch.setattr(september, "handle", original)
    return record, sent


def _id_map(intent: dict, mint_seed: str) -> dict:
    names = {value: f"<{key}>" for key, value in intent.items() if key != "task_text" and isinstance(value, str)}
    for prefix in ("hold", "receipt", "release"):
        for n in range(1, 13):
            names[september.make_id(mint_seed, prefix, n)] = f"<{prefix}:{n}>"
    return names


def _normal(value, names):
    if isinstance(value, dict):
        # A payload hash covers the trial's own identities, so it differs between any two trials by construction.
        return {key: _normal(item, names) for key, item in value.items() if key != "payload_hash"}
    if isinstance(value, (list, tuple)):
        return [_normal(item, names) for item in value]
    return names.get(value, value) if isinstance(value, str) else value


def _translate(tool, request, to_v2: dict) -> dict:
    """The September broker's flat request as the v2 session sends it (identities, plus a payload for a write)."""
    body = _normal(request, to_v2)
    if tool in ("get_booking", "list_holds", "get_move_status"):
        return {"booking_id": body["booking_id"], "payload": None}
    identities = {"booking_id": body["booking_id"]}
    if tool == "move_booking":
        identities["operation_id"] = body["operation_id"]
    if tool == "release_hold":
        identities["hold_id"] = body["hold_id"]
    return {**identities, "payload": body}


BUSINESS_EVENTS = ("hold_created", "hold_expired", "hold_released", "hold_consumed", "move_accepted", "move_succeeded", "move_failed")
COMMON_EVENTS = BUSINESS_EVENTS + ("http_attempt", "fault_triggered", "request_rejected", "world_stopped", "observer_advanced")


def _final_view(snapshot: dict, names: dict) -> dict:
    events = [event for event in snapshot["events"] if event["type"] in COMMON_EVENTS]
    return _normal({
        "tick": snapshot["tick"], "attempts": snapshot["attempts"], "waits": snapshot["waits"], "stopped": snapshot["stopped"],
        "decision_tick": snapshot["decision_tick"], "booking": snapshot["booking"], "history": snapshot["history"],
        "holds": snapshot["holds"], "move": snapshot["move"],
        "faults": [{key: f[key] for key in ("fault_id", "triggered", "trigger_tick", "call_id", "attempt_id", "reason")}
                   for f in snapshot["fault_executions"]],
        "events": [(event["tick"], event["type"], event["call_id"]) for event in events],
        "business": [(event["type"], {key: value for key, value in event["payload"].items() if key != "attempt_id"})
                     for event in events if event["type"] in BUSINESS_EVENTS]}, names)


class InProcessWorld:
    def __init__(self, tmp_path, case, namespace):
        scenario = PACK.scenario(case["case_id"])
        self.transport = KernelTransport(WorldStore(tmp_path, PACK.handler_factory()), KernelLimits())
        self.intent = PACK.allocate_intent(scenario.fixture_id, namespace)
        handle = self.transport.create(namespace, self.intent, scenario.fault_spec.model_dump(mode="json"), scenario.fixture_id)
        self.world_id, self.capability = handle["world_id"], handle["capability"]

    def send(self, tool, request, call_id, attempt_id):
        return dispatch(self.transport.store, self.transport.limits, world=self.world_id, capability=self.capability, call=call_id,
                        attempt=attempt_id, tool=tool, service=m.SERVICE_OF_TOOL[tool], request=request)

    def finish(self):
        self.transport.stop(self.world_id)
        self.transport.advance(self.world_id, 5, observer=True)
        return self.transport.snapshot(self.world_id)


class HttpWorld:
    ROUTES = {"get_booking": ("get", "/business/bookings/{booking_id}"), "list_holds": ("get", "/business/holds"),
              "get_move_status": ("get", "/business/bookings/{booking_id}/moves/{operation_id}"),
              "place_hold": ("post", "/business/holds"), "move_booking": ("post", "/business/bookings/{booking_id}/moves"),
              "release_hold": ("post", "/business/holds/{hold_id}/release")}

    def __init__(self, tmp_path, case, namespace):
        from fastapi.testclient import TestClient
        scenario = PACK.scenario(case["case_id"])
        self.client = TestClient(PACK.app(database_dir=tmp_path, control_token="token"))
        self.intent = PACK.allocate_intent(scenario.fixture_id, namespace)
        created = self.client.post("/control/worlds", headers={"X-FaultLab-Control": "token"},
                                   json={"episode_id": namespace, "intent": self.intent, "fixture_id": scenario.fixture_id,
                                         "fault_spec": scenario.fault_spec.model_dump(mode="json")})
        assert created.status_code == 201, created.text
        self.world_id, self.capability = created.json()["world_id"], created.json()["capability"]

    def send(self, tool, request, call_id, attempt_id):
        method, path = self.ROUTES[tool]
        payload = request.get("payload") or {}
        url = path.format(booking_id=request["booking_id"], hold_id=payload.get("hold_id"),
                          operation_id=self.intent["move_operation_id"])
        headers = {"X-FaultLab-World": self.world_id, "X-FaultLab-Capability": self.capability, "X-FaultLab-Call": call_id,
                   "X-FaultLab-Attempt": attempt_id}
        response = self.client.request(method, url, headers=headers, json=payload if method == "post" else None,
                                       params={"booking_id": request["booking_id"]} if tool == "list_holds" else None)
        return response.status_code, response.json(), None

    def finish(self):
        control = {"X-FaultLab-Control": "token"}
        assert self.client.post(f"/control/worlds/{self.world_id}/stop", headers=control).status_code == 200
        assert self.client.post(f"/control/worlds/{self.world_id}/advance", headers=control, json={"ticks": 5, "observer": True}).status_code == 200
        return self.client.get(f"/control/worlds/{self.world_id}/snapshot", headers=control).json()


def _parity(world_class, tmp_path, agent_name, factory, case, seed_text, monkeypatch):
    record, sent = _september_run(factory, case, seed_text, monkeypatch)
    namespace = f"parity-{case['case_id']}-{seed_text}-{agent_name}"
    v2 = world_class(tmp_path / namespace, case, namespace)
    sept_names = _id_map(record["intent"], f"world|{case['case_id']}|{seed_text}")      # the September driver's world seed
    v2_names = _id_map(v2.intent, "world|" + v2.intent["task_id"])
    v2_by_name = {name: value for value, name in v2_names.items()}
    to_v2 = {value: v2_by_name[name] for value, name in sept_names.items() if name in v2_by_name}
    for step, item in enumerate(sent):
        answer = item["answer"]
        status, result, delay = v2.send(item["tool"], _translate(item["tool"], item["request"], to_v2), item["ctx"]["call_id"],
                                        item["ctx"]["attempt_id"])
        where = f"{agent_name} {case['case_id']} {seed_text} step {step} {item['tool']}"
        assert status == answer["http_status"], where
        assert result["error_code"] == answer["error_code"], where
        assert _normal(result["data"], v2_names) == _normal(answer["data"], sept_names), where
        if delay is not None:
            assert round(delay * 1000) == answer["lost_ms"], where
    assert _final_view(v2.finish(), v2_names) == _final_view(record["horizon"], sept_names), f"{agent_name} {case['case_id']} {seed_text}"
    return len(sent)


def test_the_kernel_world_answers_every_september_request_alike_and_ends_in_the_same_state(tmp_path, monkeypatch):
    sent = 0
    for agent_name, factory in _agents().items():
        for case in CASES:
            for seed_text in driver.trial_seeds(case):
                sent += _parity(InProcessWorld, tmp_path, agent_name, factory, case, seed_text, monkeypatch)
    assert sent > 600            # every agent, case and seed sent its requests through both worlds


def test_the_same_requests_over_http_give_the_same_answers_and_state(tmp_path, monkeypatch):
    for case in CASES:
        _parity(HttpWorld, tmp_path, "reference", reference.ReferenceAgent, case, driver.trial_seeds(case)[0], monkeypatch)
    for agent_name in ("blind_retry_create", "give_up_after_timeout"):
        _parity(HttpWorld, tmp_path, agent_name, mutants.MUTANTS[agent_name], CASES[1], driver.trial_seeds(CASES[1])[0], monkeypatch)


# -- the kernel's new families and refusal bodies ---------------------------------------------------------

def _world(tmp_path, primitives, fixture="standard-v1", namespace="kernel"):
    spec = {"schema_version": "faultlab/v1", "scope": PACK.pack_id, "seed": 1,
            "primitives": [{"target_service": m.SERVICE_OF_TOOL[p["target_tool"]], "occurrence": 1, **p} for p in primitives]}
    store = WorldStore(tmp_path, PACK.handler_factory())
    intent = PACK.allocate_intent(fixture, namespace)
    handle = store.create(namespace, intent, spec, fixture)
    counter = iter(range(1, 100))

    def send(tool, payload=None, **identities):
        n = next(counter)
        return dispatch(store, KernelLimits(), world=handle["world_id"], capability=handle["capability"], call=f"call-{n}",
                        attempt=f"attempt-{n}", tool=tool, service=m.SERVICE_OF_TOOL[tool],
                        request={"booking_id": intent["booking_id"], **identities, "payload": payload})
    return store, handle["world_id"], intent, send


def test_f5_commits_the_hold_then_answers_500_with_no_data(tmp_path):
    store, world_id, intent, send = _world(tmp_path, [{"kind": "F5", "target_tool": "place_hold", "parameters": {}}])
    status, result, delay = send("place_hold", {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]})
    assert (status, result["error_code"], result["data"], delay) == (500, "INTERNAL_ERROR", None, 0.0)
    state = store.read(world_id)
    assert [hold["state"] for hold in state["pack"]["holds"]] == ["ACTIVE"]
    assert state["fault_executions"][0]["triggered"] is True


def test_a_refusal_carries_its_body_and_f4_pre_empts_the_other_faults_of_the_attempt(tmp_path):
    store, world_id, intent, send = _world(tmp_path / "a", [{"kind": "F6", "target_tool": "place_hold", "parameters": {"ttl_cut_ticks": 9}}])
    status, hold, _ = send("place_hold", {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]})
    hold_id = hold["data"]["hold_id"]
    status, result, _ = send("move_booking", {"booking_id": intent["booking_id"], "hold_id": hold_id,
                                              "operation_id": intent["move_operation_id"], "idempotency_key": intent["move_idempotency_key"],
                                              "intent_hash": intent["move_intent_hash"]}, operation_id=intent["move_operation_id"])
    assert (status, result["error_code"], result["data"]) == (409, "HOLD_NOT_ACTIVE", {"hold_id": hold_id, "hold_state": "EXPIRED"})
    store, world_id, intent, send = _world(tmp_path / "b", [
        {"kind": "F4", "target_tool": "place_hold", "parameters": {"failure_count": 1}},
        {"kind": "F6", "target_tool": "place_hold", "parameters": {"ttl_cut_ticks": 3}}])
    assert send("place_hold", {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]})[0] == 503
    reasons = [(f["triggered"], f["reason"]) for f in store.read(world_id)["fault_executions"]]
    assert reasons == [(True, None), (False, "pre_effect_failure")]


def test_the_bookings_grammar_is_the_september_one(tmp_path):
    with pytest.raises(WorldError) as refused:
        _world(tmp_path / "a", [{"kind": "F1", "target_tool": "move_booking", "parameters": {"response_delay_ms": 1500}},
                                {"kind": "F2", "target_tool": "move_booking", "parameters": {"completion_delay_ticks": 2,
                                                                                            "terminal_status": "FAILED"}}])
    assert refused.value.code == "CONFLICTING_MOVE_FAULTS"
    with pytest.raises(WorldError) as refused:
        _world(tmp_path / "b", [{"kind": "F3", "target_tool": "get_booking", "parameters": {"versions_back": 1}}])
    assert refused.value.code == "STALE_HISTORY_UNAVAILABLE"
    with pytest.raises(WorldError) as refused:
        _world(tmp_path / "c", [{"kind": "F6", "target_tool": "release_hold", "parameters": {"ttl_cut_ticks": 1}}])
    assert refused.value.code == "TARGET_NOT_ALLOWED"


@pytest.mark.parametrize("primitive", [
    {"kind": "F5", "target_tool": "update_order", "target_service": "orders", "occurrence": 1, "parameters": {}},
    {"kind": "F6", "target_tool": "update_order", "target_service": "orders", "occurrence": 1, "parameters": {"ttl_cut_ticks": 1}}])
def test_the_orders_world_refuses_the_new_families(tmp_path, primitive):
    store = WorldStore(tmp_path, ORDERS.handler_factory())
    spec = {"schema_version": "faultlab/v1", "scope": ORDERS.pack_id, "seed": 1, "primitives": [primitive]}
    with pytest.raises(WorldError) as refused:
        store.create("orders-f5", ORDERS.example_intent("standard-v1"), spec, "standard-v1")
    assert (refused.value.code, refused.value.status) == ("INVALID_FAULT_SPEC", 422)


# -- the session's resend rule ----------------------------------------------------------------------------

def _session(tmp_path, pack, scenario_id, namespace="session"):
    scenario = pack.scenario(scenario_id)
    transport = KernelTransport(WorldStore(tmp_path, pack.handler_factory()), KernelLimits())
    intent = pack.allocate_intent(scenario.fixture_id, namespace)
    world = transport.create(namespace, intent, scenario.fault_spec.model_dump(mode="json"), scenario.fixture_id)
    plan = pack.plan(scenario_id, agent=AGENT, environment=ENV, protocol_version="faultlab/v1", caps=Caps(http_attempts=18))
    return TrialSession(pack=pack, plan=plan, attempt_id=namespace, world_id=world["world_id"], intent=intent, transport=transport,
                        journal=Journal(namespace=namespace), caps=plan.caps), transport, world["world_id"], intent


def test_a_lost_place_hold_answer_reaches_the_agent_once_and_is_never_resent(tmp_path):
    session, transport, world_id, intent = _session(tmp_path, PACK, "hk-dev-2")
    observation = asyncio.run(session.call("place_hold", {"booking_id": intent["booking_id"],
                                                          "payload": {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]}}))
    assert observation.transport == "timeout" and observation.result["error_code"] == "HTTP_TIMEOUT"
    assert len(session.calls[-1]["attempt_ids"]) == 1 and session.usage.http_attempts == 1
    holds = asyncio.run(session.call("list_holds", {"booking_id": intent["booking_id"]})).result["data"]["holds"]
    assert [hold["state"] for hold in holds] == ["ACTIVE"]          # the hold exists; only listing it shows it


def test_a_503_before_any_effect_is_resent_once_and_keyed_writes_keep_their_resend(tmp_path):
    session, transport, world_id, intent = _session(tmp_path / "a", PACK, "hk-dev-7")
    hold = asyncio.run(session.call("place_hold", {"booking_id": intent["booking_id"],
                                                   "payload": {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]}}))
    hold_id = hold.result["data"]["hold_id"]
    move = {"booking_id": intent["booking_id"], "hold_id": hold_id, "operation_id": intent["move_operation_id"],
            "idempotency_key": intent["move_idempotency_key"], "intent_hash": intent["move_intent_hash"]}
    asyncio.run(session.call("move_booking", {"booking_id": intent["booking_id"], "operation_id": intent["move_operation_id"], "payload": move}))
    released = asyncio.run(session.call("release_hold", {"booking_id": intent["booking_id"], "hold_id": hold_id,
                                                         "payload": {"booking_id": intent["booking_id"], "hold_id": hold_id}}))
    assert len(session.calls[-1]["attempt_ids"]) == 2 and released.result["error_code"] == "TRANSIENT_UNAVAILABLE"
    # The orders writes are keyed: a lost upgrade answer is still resent with the same bytes, as before.
    session, transport, world_id, intent = _session(tmp_path / "b", ORDERS, "dev-2")
    payload = {"order_id": intent["order_id"], "desired_shipping": "express", "expected_version": intent["expected_version"],
               "operation_id": intent["upgrade_operation_id"], "idempotency_key": intent["upgrade_idempotency_key"],
               "intent_hash": intent["upgrade_intent_hash"]}
    asyncio.run(session.call("update_order", {"order_id": intent["order_id"], "operation_id": intent["upgrade_operation_id"],
                                              "payload": payload}))
    assert len(session.calls[-1]["attempt_ids"]) == 2


# -- short hold labels and the lab's refusal of a hold it never delivered -----------------------------------

ORDERS_DIGEST = "6956e1d5754ac96e8130b4f62aa733707391d690b118ce7b18738b3f6920f961"     # before the second task, 2026-11-15


def test_the_order_pack_identity_did_not_move_and_only_bookings_declares_labels():
    assert ORDERS.digest() == ORDERS_DIGEST and "references" not in ORDERS.manifest()
    assert PACK.manifest()["references"] == {"key": "hold_id", "prefix": "hold-", "sources": ["list_holds", "place_hold"],
                                             "refusal_code": "UNKNOWN_HOLD_REFERENCE"}


def _place(session, intent):
    return asyncio.run(session.call("place_hold", {"booking_id": intent["booking_id"],
                                                   "payload": {"booking_id": intent["booking_id"], "slot_id": intent["target_slot"]}}))


def _release(session, intent, hold):
    return asyncio.run(session.call("release_hold", {"booking_id": intent["booking_id"], "hold_id": hold,
                                                     "payload": {"booking_id": intent["booking_id"], "hold_id": hold}}))


def test_the_agent_sees_short_hold_labels_and_the_world_gets_the_real_ids(tmp_path):
    session, transport, world_id, intent = _session(tmp_path, PACK, "hk-dev-1")
    assert _place(session, intent).result["data"]["hold_id"] == "hold-1"
    real = transport.state(world_id)["pack"]["holds"][0]["hold_id"]
    assert real != "hold-1" and session.reference_labels == {"hold-1": real}
    listed = asyncio.run(session.call("list_holds", {"booking_id": intent["booking_id"]}))
    assert [hold["hold_id"] for hold in listed.result["data"]["holds"]] == ["hold-1"]
    move = {"booking_id": intent["booking_id"], "hold_id": "hold-1", "operation_id": intent["move_operation_id"],
            "idempotency_key": intent["move_idempotency_key"], "intent_hash": intent["move_intent_hash"]}
    moved = asyncio.run(session.call("move_booking", {"booking_id": intent["booking_id"], "operation_id": intent["move_operation_id"],
                                                      "payload": move}))
    assert moved.result["data"]["status"] == "SUCCEEDED" and moved.result["data"]["hold_id"] == "hold-1"
    assert moved.result["data"]["receipt"]["hold_id"] == "hold-1" and move["hold_id"] == "hold-1"   # the adapter's dict is untouched
    assert transport.state(world_id)["pack"]["move"]["hold_id"] == real
    labelled = [e for e in session.events if e.kind == "reference_labelled"]
    assert [e.plane for e in labelled] == ["evaluator"]


def test_a_hold_the_lab_never_delivered_is_refused_with_no_http_attempt(tmp_path):
    session, transport, world_id, intent = _session(tmp_path, PACK, "hk-dev-2")
    assert _place(session, intent).transport == "timeout"                      # the hold exists, its label does not yet
    attempts = transport.state(world_id)["attempts"]
    real = transport.state(world_id)["pack"]["holds"][0]["hold_id"]
    for guess in ("hold-1", real):                                            # a guessed label, or the raw id it would stand for
        refused = _release(session, intent, guess)
        assert refused.result == {"call_id": refused.call_id, "tool": "release_hold", "transport": "error",
                                  "error_code": "UNKNOWN_HOLD_REFERENCE", "hold_id": guess}
        assert session.calls[-1]["attempt_ids"] == [] and refused.http_status is None
    assert transport.state(world_id)["attempts"] == attempts and session.usage.http_attempts == 1
    assert [e.kind for e in session.events].count("scope_refusal") == 2
    asyncio.run(session.call("list_holds", {"booking_id": intent["booking_id"]}))
    released = _release(session, intent, "hold-1")
    assert released.result["data"]["effect"] == "released" and transport.state(world_id)["pack"]["holds"][0]["state"] == "RELEASED"
