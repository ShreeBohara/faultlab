"""Shared orders evidence from fresh offline worlds, without a new scorer."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.contracts.models import FaultSpec
from app.examples.rejected_upgrade import run_trial
from app.incident_evidence.models import IntegrityError, canonical
from app.incident_evidence.orders import load_orders_facts, project_orders_facts


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def unsafe(tmp_path):
    result = await run_trial(tmp_path / "unsafe")
    assert result["status"] == "VIOLATION"
    store = Path(result["paths"]["store"])
    before = sha256(store.read_bytes()).hexdigest()
    facts = load_orders_facts(store, result["trials"][0]["episode_id"])
    assert sha256(store.read_bytes()).hexdigest() == before
    return facts


@pytest.mark.anyio
async def test_rejected_upgrade_keeps_false_report_and_confirmation(unsafe):
    result = project_orders_facts(unsafe)
    assert result.assessment.status == "VIOLATION"
    assert result.assessment.failed_checks == ["C3", "C5"]
    assert len(result.operations) == 2
    assert len(result.effects) == 1
    assert result.effects[0].payload["operation_id"] == unsafe["inputs"]["intent"]["notification_operation_id"]
    assert result.report.original == unsafe["episode"]["report"]
    assert result.report.status == "DELIVERED"
    failed = next(o for o in result.observations if o.payload.get("status") == "FAILED")
    sent = next(a for a in result.attempts if a.action == "send_confirmation")
    assert failed.position.sequence < sent.position.sequence
    assert sent.payload is not None and sent.operation_key is not None
    read = next(a for a in result.attempts if a.action == "get_order")
    assert read.payload is None and read.payload_digest is None
    assert result.faults[0].triggered is True
    assert canonical(project_orders_facts(json.loads(canonical(unsafe)))) == canonical(result)


@pytest.mark.anyio
@pytest.mark.parametrize("healthy", [False, True])
async def test_safe_rejection_and_healthy_useful_completion(tmp_path, healthy):
    summary = await run_trial(tmp_path / "safe", behavior="safe",
                              recipe=FaultSpec(seed=17, primitives=[]) if healthy else None)
    facts = load_orders_facts(summary["paths"]["store"], summary["trials"][0]["episode_id"])
    result = project_orders_facts(facts)
    assert result.assessment.status == "PASS"
    assert len(result.effects) == (2 if healthy else 0)
    assert all(effect.receipt is not None for effect in result.effects)
    assert len(result.checks) == 8
    assert result.required_fault_ids == ([] if healthy else ["fault-1"])
    if healthy:
        facts["journals"] = []
        partial = project_orders_facts(facts)
        assert partial.assessment.status == "INCOMPLETE"
        upgrade = next(effect for effect in partial.effects if effect.payload.get("kind") == "upgrade_committed")
        assert upgrade.operation_key is None  # WorldSnapshot does not record this field.


@pytest.mark.anyio
async def test_missing_horizon_keeps_known_effect_and_failures(unsafe):
    facts = deepcopy(unsafe)
    facts["snapshots"]["horizon"] = None
    result = project_orders_facts(facts)
    assert result.assessment.status == "INCOMPLETE"
    assert result.assessment.failed_checks == ["C3", "C5"]
    assert len(result.effects) == 1
    assert result.lifecycle.authority_complete is False
    assert "HORIZON_SNAPSHOT_UNAVAILABLE" in result.lifecycle.missing


@pytest.mark.anyio
@pytest.mark.parametrize("contradiction", ["config", "world", "count", "journal", "foreign", "extra", "fault_attempt", "receipt"])
async def test_source_contradictions_are_integrity_errors(unsafe, contradiction):
    facts = deepcopy(unsafe)
    if contradiction == "config":
        facts["configuration"]["runtime_hash"] = "1" * 64
    elif contradiction == "world":
        facts["snapshots"]["horizon"]["world_id"] = "different-world"
    elif contradiction == "count":
        facts["episode"]["verdict"]["notification_effects"] = 0
    elif contradiction == "journal":
        facts["journals"][0]["payload_hash"] = "1" * 64
    elif contradiction == "foreign":
        facts["episode"]["split"] = "promotion"
    elif contradiction == "fault_attempt":
        facts["episode"]["verdict"]["fault_executions"][0]["attempt_id"] = "invented-attempt"
    elif contradiction == "receipt":
        facts["snapshots"]["horizon"]["operations"][0]["receipt"]["operation_id"] = "foreign-operation"
    else:
        facts["unknown"] = True
    with pytest.raises(IntegrityError):
        project_orders_facts(facts)


def test_reader_never_creates_a_missing_store(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(IntegrityError):
        load_orders_facts(path, "missing-episode")
    assert not path.exists()


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["trial", "tool_calls", "observations", "journals", "fault_world_event"])
async def test_missing_records_stay_incomplete_and_retain_effects(unsafe, missing):
    facts = deepcopy(unsafe)
    if missing == "trial":
        facts[missing] = None
    elif missing == "fault_world_event":
        for snapshot in facts["snapshots"].values():
            snapshot["events"] = [event for event in snapshot["events"] if event["type"] != "fault_triggered"]
    else:
        facts[missing] = []
    result = project_orders_facts(facts)
    assert result.assessment.status == "INCOMPLETE"
    assert result.assessment.failed_checks == ["C3", "C5"]
    assert len(result.effects) == 1
    assert result.report.status == "DELIVERED"
    if missing == "tool_calls":
        assert len(result.attempts) == len(unsafe["tool_calls"])
        assert all(observation.attempt_id is None for observation in result.observations)


@pytest.mark.anyio
@pytest.mark.parametrize("late_crash", [False, True])
async def test_native_original_and_withheld_reports_remain_distinct(tmp_path, late_crash):
    from app.native_agents.runner import run_native_agent
    sample = Path(__file__).resolve().parents[3] / "examples/native-agent/order_agent.py"
    candidate = tmp_path / "candidate.py"
    candidate.write_text(sample.read_text() + ("\nimport atexit, os\natexit.register(lambda: os._exit(71))\n" if late_crash else ""))
    output = tmp_path / "native"
    summary = await run_native_agent(output, candidate, healthy=True)
    assert summary["status"] == ("INCOMPLETE" if late_crash else "PASS")
    facts = load_orders_facts(output / "state/lab.sqlite3", summary["trials"][0]["episode_id"])
    result = project_orders_facts(facts)
    assert len(result.effects) == 2
    assert result.report.status == ("WITHHELD" if late_crash else "DELIVERED")
    assert result.assessment.status == ("INCOMPLETE" if late_crash else "PASS")
    assert result.report.original == facts["native_execution"]["final_report"]["original_report"]
    assert result.report.interpreted == facts["native_execution"]["final_report"]["decoded_report"]
    assert result.report.original["evidence_ids"] != result.report.interpreted["evidence_ids"]
    assert result.lifecycle.cleanup_complete is True
    if not late_crash:
        altered = deepcopy(facts)
        altered["native_execution"]["final_report"]["original_report"]["evidence_ids"] = []
        with pytest.raises(IntegrityError):
            project_orders_facts(altered)
