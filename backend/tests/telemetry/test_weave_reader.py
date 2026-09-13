import asyncio
import copy

import pytest

from app.telemetry.weave_reader import TraceRegistration, WeaveReader


def records(metadata):
    root = {"id": "root", "project_id": "fixture/project", "parent_id": None, "trace_id": "trace",
            "attributes": metadata, "inputs": {"task": "fixture"}, "output": {"terminal_status": "COMPLETED", "report": {}},
            "ended_at": "2026-09-12T00:00:00+00:00", "exception": None}
    child = {**copy.deepcopy(root), "id": "child", "parent_id": "root", "output": {"observation": {"evidence_id": "ev"}}}
    return [root, child]


def test_verified_exact_inventory_and_immutable_digest(worker, metadata):
    worker.calls = records(metadata)
    registration = TraceRegistration("fixture/project", metadata, "root", ("child",))
    result = asyncio.run(WeaveReader(worker, "fixture/project", lambda _: True).read(registration))
    assert result.status == "weave_verified" and result.ingestion_state == "INGESTED"
    assert result.snapshot["child_call_ids"] == ["child"] and len(result.snapshot["digest"]) == 64
    assert [x[0] for x in worker.commands] == ["flush", "get_calls"]


@pytest.mark.parametrize("change", ["foreign_project", "episode", "duplicate", "parent", "private", "output"])
def test_rejects_invalid_remote_records(worker, metadata, change):
    worker.calls = records(metadata)
    if change == "foreign_project": worker.calls[0]["project_id"] = "other/project"
    if change == "episode": worker.calls[1]["attributes"]["episode_id"] = "foreign"
    if change == "duplicate": worker.calls.append(worker.calls[1])
    if change == "parent": worker.calls[1]["parent_id"] = "foreign"
    if change == "private": worker.calls[1]["output"]["private_snapshot"] = {}
    if change == "output": worker.calls[1]["output"] = {}
    result = asyncio.run(WeaveReader(worker, "fixture/project", lambda _: True).read(
        TraceRegistration("fixture/project", metadata, "root", ("child",))))
    assert result.status == "weave_error" and result.ingestion_state == "REJECTED"


@pytest.mark.parametrize("split,purpose", [("promotion", "promotion"), ("final_audit", "portability"), ("development", "discovery")])
def test_rejects_before_network(worker, metadata, split, purpose):
    metadata.update(split=split, experiment_purpose=purpose)
    result = asyncio.run(WeaveReader(worker, "fixture/project", lambda _: False).read(
        TraceRegistration("fixture/project", metadata, "root")))
    assert result.error_code == "NOT_AUTHORIZED" and worker.commands == []


def test_missing_child_polls_bounded_without_model_retry(worker, metadata):
    worker.calls = records(metadata)[:1]
    now = [0.0]
    async def sleep(seconds): now[0] += seconds
    result = asyncio.run(WeaveReader(worker, "fixture/project", lambda _: True, deadline_seconds=5,
        clock=lambda: now[0], sleep=sleep).read(TraceRegistration("fixture/project", metadata, "root", ("child",))))
    assert result.status == "weave_pending" and result.error_code == "DEADLINE"
    assert [r[2] for r in worker.commands if r[0] == "get_calls"] == [5, 3, 1]
    assert all(r[0] in {"flush", "get_calls"} for r in worker.commands)


def test_flush_consumes_entire_deadline(worker, metadata):
    now = [0.0]
    async def request(command, payload, **kwargs):
        assert command == "flush"
        now[0] = 60
    worker.request = request
    result = asyncio.run(WeaveReader(worker, "fixture/project", lambda _: True, clock=lambda: now[0]).read(
        TraceRegistration("fixture/project", metadata, "root")))
    assert result.status == "weave_pending"


def test_authority_rechecked_before_result(worker, metadata):
    worker.calls = records(metadata)
    checks = []
    def authorize(_):
        checks.append(1)
        return len(checks) < 3
    result = asyncio.run(WeaveReader(worker, "fixture/project", authorize).read(
        TraceRegistration("fixture/project", metadata, "root", ("child",))))
    assert result.status == "weave_error"
