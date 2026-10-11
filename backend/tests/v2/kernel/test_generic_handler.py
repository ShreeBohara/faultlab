"""The kernel is task-agnostic: a handler with its own tools, services, histories and effects.

A two-tool "ledger" pack: ``post`` (a write on service ``ledger``, idempotent by key) and
``balance`` (a read). The kernel places F4 and F1 by ``(tool, service, occurrence)`` and keeps
the budgets, clock, event log and histories without knowing what a ledger is.
"""
import sqlite3

import pytest
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from faultlab.env.kernel import KernelLimits, WorldError, WorldHandler, WorldStore, create_app, dispatch

CTRL = {'X-FaultLab-Control': 'test-control'}


class LedgerHandler(WorldHandler):
    pack_id = "ledger.post_then_balance/v1"
    fixtures = ("empty-v1",)
    history_tables = ("postings",)

    def validate_intent(self, intent):
        if set(intent) != {"account"} or not isinstance(intent["account"], str):
            raise WorldError("INVALID_INTENT", 422)
        return dict(intent)

    def initial_state(self, intent, fixture_id):
        return {"balance": 0, "postings": [], "keys": {}}

    def validate_schedule(self, spec, state):
        for primitive in spec["primitives"]:
            if primitive["target_tool"] not in ("post", "balance") or primitive["target_service"] != "ledger":
                raise WorldError("INVALID_FAULT_SPEC", 422)

    def histories(self, state):
        return {"postings": [(posting["key"], posting) for posting in state["pack"]["postings"]]}

    def perform(self, ctx, state, tool, service, request, faults):
        pack = state["pack"]
        if tool == "balance":
            return 200, {"call_id": ctx.call_id, "tool": tool, "transport": "ok", "balance": pack["balance"]}, False
        key, amount = request["payload"]["key"], request["payload"]["amount"]
        if key in pack["keys"]:
            if pack["keys"][key] != amount:
                raise WorldError("IDEMPOTENCY_CONFLICT")
            return 200, {"call_id": ctx.call_id, "tool": tool, "transport": "ok", "balance": pack["balance"], "replayed": True}, True
        pack["keys"][key] = amount
        pack["balance"] += amount
        pack["postings"].append({"key": key, "amount": amount, "tick": state["tick"]})
        ctx.event("posting_committed", {"key": key, "amount": amount})
        return 201, {"call_id": ctx.call_id, "tool": tool, "transport": "ok", "balance": pack["balance"]}, True

    def snapshot(self, state):
        return {"world_id": state["world_id"], "tick": state["tick"], "balance": state["pack"]["balance"],
                "postings": state["pack"]["postings"], "events": state["events"]}


def ledger_router(store, limits):
    api = APIRouter(prefix="/ledger")

    async def run(request, tool, payload=None):
        status, result, delay = dispatch(store, limits, world=request.headers.get("X-FaultLab-World", ""),
                                         capability=request.headers.get("X-FaultLab-Capability", ""),
                                         call=request.headers.get("X-FaultLab-Call", ""), attempt=request.headers.get("X-FaultLab-Attempt", ""),
                                         tool=tool, service="ledger", request={"payload": payload})
        assert delay == 0.0 or tool == "post"
        return JSONResponse(status_code=status, content=result)

    @api.post("/post")
    async def post(request: Request):
        return await run(request, "post", await request.json())

    @api.get("/balance")
    async def balance(request: Request):
        return await run(request, "balance")
    return api


@pytest.fixture
def world(tmp_path):
    app = create_app(handler=LedgerHandler(), database_dir=tmp_path, control_token="test-control",
                     limits=KernelLimits(http_attempts=6, ticks=6, waits=1, wait_ticks=2), business_router=ledger_router)
    client = TestClient(app)

    def create(primitives=()):
        response = client.post("/control/worlds", headers=CTRL, json={"episode_id": "ep-1", "intent": {"account": "acct-1"},
                               "fault_spec": {"seed": 3, "scope": "ledger.post_then_balance/v1", "primitives": list(primitives)},
                               "fixture_id": "empty-v1"})
        assert response.status_code == 201, response.text
        handle = response.json()
        return client, handle, {"X-FaultLab-World": handle["world_id"], "X-FaultLab-Capability": handle["capability"],
                                "X-FaultLab-Call": "call-1", "X-FaultLab-Attempt": "attempt-1"}
    return create


def test_a_foreign_pack_runs_on_the_kernel_with_its_own_tools_and_histories(world, tmp_path):
    client, handle, headers = world()
    assert client.get("/health").json()["pack"] == "ledger.post_then_balance/v1"
    assert client.post("/ledger/post", json={"key": "k1", "amount": 5}, headers=headers).status_code == 201
    replay = client.post("/ledger/post", json={"key": "k1", "amount": 5}, headers=headers | {"X-FaultLab-Attempt": "attempt-2"})
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    conflict = client.post("/ledger/post", json={"key": "k1", "amount": 6}, headers=headers | {"X-FaultLab-Attempt": "attempt-3"})
    assert conflict.status_code == 409 and conflict.json()["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert client.get("/ledger/balance", headers=headers).json()["balance"] == 5
    snapshot = client.get(f"/control/worlds/{handle['world_id']}/snapshot", headers=CTRL).json()
    assert snapshot["balance"] == 5 and snapshot["tick"] == 4 and [p["key"] for p in snapshot["postings"]] == ["k1"]
    assert [e["type"] for e in snapshot["events"]][:3] == ["http_attempt", "posting_committed", "http_attempt"]
    with sqlite3.connect(tmp_path / (handle["world_id"] + ".sqlite3")) as db:
        assert db.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM postings")
    assert WorldStore(tmp_path, LedgerHandler()).snapshot(handle["world_id"])["balance"] == 5


def test_kernel_budgets_and_faults_apply_without_pack_knowledge(world):
    client, handle, headers = world([{"kind": "F4", "target_tool": "post", "target_service": "ledger", "occurrence": 1,
                                      "parameters": {"failure_count": 2}},
                                     {"kind": "F1", "target_tool": "post", "target_service": "ledger", "occurrence": 3,
                                      "parameters": {"response_delay_ms": 1500}}])
    first = client.post("/ledger/post", json={"key": "k1", "amount": 1}, headers=headers)
    second = client.post("/ledger/post", json={"key": "k1", "amount": 1}, headers=headers | {"X-FaultLab-Attempt": "attempt-2"})
    assert (first.status_code, second.status_code) == (503, 503) and first.json()["error_code"] == "TRANSIENT_UNAVAILABLE"
    assert client.get("/ledger/balance", headers=headers).json()["balance"] == 0
    third = client.post("/ledger/post", json={"key": "k1", "amount": 1}, headers=headers | {"X-FaultLab-Attempt": "attempt-3"})
    assert third.status_code == 201
    faults = client.get(f"/control/worlds/{handle['world_id']}/faults", headers=CTRL).json()
    assert faults[0]["triggered"] and faults[0]["attempt_id"] == "attempt-1"
    assert faults[1]["triggered"] and faults[1]["attempt_id"] == "attempt-3" and faults[1]["trigger_tick"] == 4
    path = f"/control/worlds/{handle['world_id']}"
    assert client.post(path + "/advance", json={"ticks": 3}, headers=CTRL).status_code == 429       # wait_ticks is 2
    assert client.post(path + "/advance", json={"ticks": 2}, headers=CTRL).json()["tick"] == 6
    assert client.post(path + "/advance", json={"ticks": 1}, headers=CTRL).status_code == 429       # one wait only
    assert client.get("/ledger/balance", headers=headers).status_code == 429                         # tick budget of 6 reached
    client.post(path + "/stop", json={}, headers=CTRL)
    assert client.post(path + "/advance", json={"ticks": 5, "observer": True}, headers=CTRL).json()["tick"] == 11


def test_bad_intents_fixtures_and_schedules_are_refused_at_creation(world):
    client, _, _ = world()
    base = {"episode_id": "ep-2", "intent": {"account": "a"}, "fault_spec": {"seed": 0, "primitives": []}, "fixture_id": "empty-v1"}
    assert client.post("/control/worlds", headers=CTRL, json=base | {"fixture_id": "other"}).json()["error_code"] == "UNKNOWN_FIXTURE"
    assert client.post("/control/worlds", headers=CTRL, json=base | {"intent": {"wrong": 1}}).json()["error_code"] == "INVALID_INTENT"
    bad = {"seed": 0, "primitives": [{"kind": "F2", "target_tool": "post", "target_service": "orders", "occurrence": 1, "parameters": {}}]}
    assert client.post("/control/worlds", headers=CTRL, json=base | {"fault_spec": bad}).json()["error_code"] == "INVALID_FAULT_SPEC"
    unknown = {"seed": 0, "primitives": [{"kind": "F9", "target_tool": "post", "target_service": "ledger", "occurrence": 1, "parameters": {}}]}
    assert client.post("/control/worlds", headers=CTRL, json=base | {"fault_spec": unknown}).status_code == 422
