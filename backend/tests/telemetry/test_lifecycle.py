import asyncio
from contextlib import contextmanager
import json
import sqlite3
import multiprocessing
import time
import threading
import pickle
from types import SimpleNamespace

import pytest

from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.safety import TelemetryError
from app.telemetry.tracing import TraceRecorder
from app.telemetry.worker import SDKHandler, CALL_COLUMNS, WeaveWorker, _serial_call
from app.config import Settings


def test_span_original_result_exception_and_correlated_children(worker, store, metadata):
    recorder = TraceRecorder(worker, TelemetryOutbox(store))
    async def run():
        async with recorder.span("run_episode", metadata, {"task": "fixture"}) as root:
            async with recorder.span("get_order", metadata, {}) as child:
                child.set_output({"observation": {"evidence_id": "fixture"}})
            root.set_output({"report": {"original": True}, "terminal_status": "COMPLETED"})
            return 42
    assert asyncio.run(run()) == 42
    starts = [p for c, p, _ in worker.commands if c == "start_call"]
    assert starts[1]["parent_id"] == starts[0]["call_id"]
    assert len(store.list_records("telemetry_outbox")) == 2
    original = ValueError("private exception never uploaded")
    async def fail():
        async with recorder.span("run_episode", metadata, {}):
            raise original
    with pytest.raises(ValueError) as caught:
        asyncio.run(fail())
    assert caught.value is original
    assert "private exception" not in json.dumps(store.list_records("trace_calls"))


@pytest.mark.parametrize("split,purpose,frozen,expected", [
    ("promotion", "promotion", False, 0), ("final_audit", "final_audit", False, 0),
    ("final_audit", "final_audit", True, 2), ("final_audit", "portability", True, 2)])
def test_split_gate_before_sdk(worker, store, metadata, split, purpose, frozen, expected):
    metadata.update(split=split, experiment_purpose=purpose, origin="faultlab_evaluation")
    async def run():
        async with TraceRecorder(worker, TelemetryOutbox(store), frozen=frozen).span("run_episode", metadata, {}):
            pass
    asyncio.run(run())
    assert len(worker.commands) == expected


def test_trace_failure_does_not_mask_actor_result(worker, store, metadata):
    worker.fail = True
    async def run():
        async with TraceRecorder(worker, TelemetryOutbox(store)).span("run_episode", metadata, {}) as span:
            span.set_output({"report": {}, "terminal_status": "COMPLETED"})
            return "original"
    assert asyncio.run(run()) == "original"
    assert store.list_records("telemetry_outbox")[0]["state"] == "PENDING"


def test_provider_failure_trace_records_only_structured_diagnostics(worker, store, metadata):
    from app.providers.runtime import RuntimeProviderError, RuntimeGeneration
    error = RuntimeProviderError("Safe provider failure", code="EMPTY_FINAL_RESPONSE", error_class="ValueError",
        finish_reason="length", generation=RuntimeGeneration("", "fixture-model", 100, 2000))
    async def run():
        async with TraceRecorder(worker, TelemetryOutbox(store)).span("run_episode", metadata, {}):
            raise error
    with pytest.raises(RuntimeProviderError) as caught:
        asyncio.run(run())
    output = store.list_records("trace_calls")[0]["output"]
    assert caught.value is error and output["provider_diagnostics"] == error.diagnostics
    assert output["report"] is None and output["terminal_status"] == "LAB_ERROR"


def test_outbox_duplicate_delivery_and_persisted_retry(store):
    outbox = TelemetryOutbox(store)
    job = outbox.enqueue("dataset", "fixture", {"rows": []})
    assert outbox.enqueue("dataset", "fixture", {"rows": []}) == job
    with pytest.raises(TelemetryError):
        outbox.enqueue("dataset", "fixture", {"rows": [1]})
    calls = []
    async def publish(payload):
        calls.append(payload)
        return "weave:///fixture/project/object/data:" + "a" * 64
    async def run():
        await outbox.deliver(job["outbox_id"], publish)
        await TelemetryOutbox(store).deliver(job["outbox_id"], publish)
    asyncio.run(run())
    assert len(calls) == 1


def test_outbox_survives_real_sqlite_reopen(tmp_path):
    class SQLiteFixtureStore:
        def __init__(self, path):
            self.db = sqlite3.connect(path)
            self.db.execute("CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(kind,id))")
        def get_record(self, kind, record_id):
            row = self.db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
            return json.loads(row[0]) if row else None
        def put_record(self, kind, record_id, payload, *, immutable=False):
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?)", (kind, record_id, json.dumps(payload)))
        def list_records(self, kind):
            return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM records WHERE kind=?", (kind,))]
    path = tmp_path / "fixture.sqlite"
    first = SQLiteFixtureStore(path)
    outbox = TelemetryOutbox(first)
    job = outbox.enqueue("trace", "call", {"report": "original"})
    outbox.update(job["outbox_id"], state="UPLOADING", attempts=1)
    first.db.close()
    second = SQLiteFixtureStore(path)
    resumed = TelemetryOutbox(second)
    resumed.recover_pending()
    record = second.get_record("telemetry_outbox", job["outbox_id"])
    assert record["payload"] == {"report": "original"} and record["state"] == "PENDING" and record["attempts"] == 1
    second.db.close()


def test_sdk_uses_attributes_before_create_and_bounded_projected_exact_ids():
    events, queries = [], []
    @contextmanager
    def attributes(values):
        events.append("attributes")
        yield
    def create(*args, **kwargs):
        events.append("create")
        return SimpleNamespace(id="root", ui_url="https://wandb.ai/fixture/project/call/root")
    def get_call(call_id, **kwargs):
        queries.append((call_id, kwargs))
        return SimpleNamespace(id=call_id)
    handler = SDKHandler(Settings(), SimpleNamespace(attributes=attributes), SimpleNamespace(create_call=create, get_call=get_call))
    handler.handle("start_call", {"name": "run_episode", "inputs": {}, "metadata": {}, "call_id": "root"})
    assert events == ["attributes", "create"]
    rows = handler.handle("get_calls", {"call_ids": [str(i) for i in range(12)]})
    assert len(rows) == 12 and [q[0] for q in queries] == [str(i) for i in range(12)]
    assert all(q[1] == {"columns": CALL_COLUMNS} for q in queries)


def test_exact_inventory_cannot_lose_children_to_duplicate_bulk_rows():
    ids = ["root", "update", "status-1", "status-2"]
    client = SimpleNamespace(
        get_calls=lambda **kwargs: [SimpleNamespace(id=value) for value in ["root", "root", "update", "update"]],
        get_call=lambda call_id, **kwargs: SimpleNamespace(id=call_id))
    handler = SDKHandler(Settings(), None, client)
    rows = handler.handle("get_calls", {"call_ids": ids})
    assert [row["id"] for row in rows] == ids


def test_exact_inventory_missing_call_stays_absent_and_requests_are_bounded():
    requests = []
    def get_call(call_id, **kwargs):
        requests.append(call_id)
        if call_id == "missing":
            raise ValueError("Call not found: fixture")
        return SimpleNamespace(id=call_id)
    handler = SDKHandler(Settings(), None, SimpleNamespace(get_call=get_call))
    assert [r["id"] for r in handler.handle("get_calls", {"call_ids": ["root", "missing"]})] == ["root"]
    for invalid in [[], ["root", "root"], [str(i) for i in range(20)]]:
        with pytest.raises(TelemetryError):
            handler.handle("get_calls", {"call_ids": invalid})
    assert requests == ["root", "missing"]


def _saved_trace_fixture():
    payload = {"call_id": "root", "name": "run_episode", "parent_id": None,
               "metadata": {"episode_id": "episode"}, "inputs": {"task": "fixture"},
               "output": {"report": {}, "terminal_status": "COMPLETED"},
               "ended_at": "2026-09-12T00:00:00+00:00"}
    call = SimpleNamespace(id="root", project_id="fixture/project", parent_id=None, trace_id="root",
        op_name="weave:///fixture/project/op/run_episode:digest", attributes=payload["metadata"],
        inputs=payload["inputs"], output=payload["output"], ended_at=payload["ended_at"], exception=None)
    return payload, call


def test_restore_completed_remote_call_never_republishes():
    payload, call = _saved_trace_fixture()
    def no_write(*args, **kwargs):
        pytest.fail("Completed exact remote evidence must not be published again")
    client = SimpleNamespace(get_call=lambda *args, **kwargs: call, create_call=no_write, finish_call=no_write)
    handler = SDKHandler(Settings(wandb_entity="fixture", wandb_project="project"), None, client)
    assert handler.handle("restore_call", payload) == {"id": "root", "reused": True}
    assert handler.calls["root"] is call


@pytest.mark.parametrize("field,value", [("project_id", "foreign/project"), ("parent_id", "foreign"),
    ("trace_id", "foreign"), ("op_name", "weave:///fixture/project/op/other:digest"),
    ("attributes", {"episode_id": "foreign"}), ("inputs", {}), ("output", {}),
    ("ended_at", "2026-09-12T01:00:00+00:00"), ("exception", "private")])
def test_restore_conflicting_remote_call_fails_before_write(field, value):
    payload, call = _saved_trace_fixture()
    setattr(call, field, value)
    def no_write(*args, **kwargs):
        pytest.fail("Conflicting evidence must not be overwritten")
    handler = SDKHandler(Settings(wandb_entity="fixture", wandb_project="project"), None,
        SimpleNamespace(get_call=lambda *args, **kwargs: call, create_call=no_write, finish_call=no_write))
    with pytest.raises(TelemetryError):
        handler.handle("restore_call", payload)


def test_restore_incomplete_remote_call_only_finishes_saved_output():
    payload, call = _saved_trace_fixture()
    call.ended_at = call.output = None
    finishes = []
    def no_create(*args, **kwargs):
        pytest.fail("An existing call must be reused")
    handler = SDKHandler(Settings(wandb_entity="fixture", wandb_project="project"), None,
        SimpleNamespace(get_call=lambda *args, **kwargs: call, create_call=no_create,
                        finish_call=lambda *args, **kwargs: finishes.append((args, kwargs))))
    assert handler.handle("restore_call", payload) == {"id": "root", "reused": False}
    assert len(finishes) == 1 and finishes[0][0] == (call,) and finishes[0][1]["output"] == payload["output"]


def test_restore_missing_call_publishes_once_and_unknown_lookup_error_never_writes():
    payload, call = _saved_trace_fixture()
    events = []
    missing_message = ["Call not found: root"]
    def get_call(*args, **kwargs):
        events.append("lookup")
        raise ValueError(missing_message[0])
    @contextmanager
    def attributes(_):
        yield
    def create(*args, **kwargs):
        events.append("create")
        return SimpleNamespace(id="root", ui_url="https://wandb.ai/fixture/project/call/root")
    handler = SDKHandler(Settings(wandb_entity="fixture", wandb_project="project"),
        SimpleNamespace(attributes=attributes), SimpleNamespace(get_call=get_call, create_call=create,
            finish_call=lambda *args, **kwargs: events.append("finish")))
    handler.handle("restore_call", payload)
    assert events == ["lookup", "create", "finish"]
    missing_message[0] = "Unexpected parsing failure"
    with pytest.raises(TelemetryError):
        handler.handle("restore_call", payload)
    assert events == ["lookup", "create", "finish", "lookup"]


def test_worker_start_rejects_without_live_authorization():
    worker = WeaveWorker(Settings())
    with pytest.raises(TelemetryError):
        asyncio.run(worker.start())
    assert worker._process is None


def test_real_weave_wrappers_do_not_serialize_client_into_ipc():
    from weave.trace.vals import WeaveDict
    transport_lock = threading.Lock()
    wrapped = WeaveDict({"report": WeaveDict({"original": True}, server=transport_lock)}, server=transport_lock)
    call = SimpleNamespace(id="fixture", output=wrapped, inputs=WeaveDict({}, server=transport_lock))
    normalized = _serial_call(call)
    assert type(normalized["output"]) is dict and type(normalized["output"]["report"]) is dict
    assert pickle.loads(pickle.dumps(normalized))["output"] == {"report": {"original": True}}


def test_hung_worker_is_terminated_at_total_deadline():
    worker = WeaveWorker(Settings())
    ctx = multiprocessing.get_context("spawn")
    worker._pipe, fixture_peer = ctx.Pipe()
    process = ctx.Process(target=time.sleep, args=(30,), daemon=True)
    worker._process = process
    process.start()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            asyncio.run(worker.request("fixture_hang", {}, timeout_seconds=0.05))
        assert time.monotonic() - started < 1
        assert not process.is_alive() and worker._process is None
    finally:
        fixture_peer.close()
        worker.abort()
