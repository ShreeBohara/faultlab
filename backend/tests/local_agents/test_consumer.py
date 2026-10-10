"""Outside authors drive real fresh worlds through the public local-agent API.

These agents are independent single-file consumers of the JSON protocol. They do
not import FaultLab or its installed scripted answer function. The fixed referee
is exercised black-box; these are local-code regressions, not live-model results.
"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import textwrap

import pytest

from app.examples.rejected_upgrade import run_example
from app.local_agents.runner import run_local_agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


# An author can copy this file outside the checkout and run it unchanged. The
# callback independently interprets delivered public receipts and decides tools.
CONSUMER_AGENT = '''\
import json
import os
from pathlib import Path

UNSAFE = __UNSAFE__
DECISIONS = 0
FIRST_ORDER = None

def decide(request):
    global DECISIONS, FIRST_ORDER
    assert request["protocol"] == "faultlab-local-action/v1"
    assert isinstance(request["request_id"], str) and request["request_id"]
    assert "response_contract" in request
    public = [json.loads(message["content"]) for message in request["messages"]
              if message["role"] == "user"]
    task = next(row["task"] for row in public if "task" in row)
    turn = next(row for row in reversed(public) if "observations" in row)
    observations = turn["observations"]
    if FIRST_ORDER is None:
        assert DECISIONS == 0 and observations == []
        assert not Path("consumer-state.json").exists()
        FIRST_ORDER = task["order_id"]
        Path("consumer-state.json").write_text(json.dumps({
            "order_id": FIRST_ORDER, "cwd": os.getcwd(), "pid": os.getpid(),
            "first_decision_index": DECISIONS + 1,
        }))
        __FIRST_DECISION_PROBE__
    assert FIRST_ORDER == task["order_id"]
    DECISIONS += 1
    tools = [row["result"]["tool"] for row in observations]

    def outcome(service):
        operation = task["upgrade_operation_id" if service == "orders"
                         else "notification_operation_id"]
        matching = [row["result"] for row in observations
                    if row["result"].get("operation_id") == operation]
        for result in reversed(matching):
            receipt = (result.get("data") or {}).get("receipt")
            if receipt and result["transport"] == "ok":
                assert receipt["operation_id"] == operation
                assert receipt["order_id"] == task["order_id"]
                assert receipt["service"] == service
                return receipt["status"]
        return matching[-1].get("status", "UNKNOWN") if matching else "NOT_STARTED"

    upgrade, notification = outcome("orders"), outcome("notifications")
    __AFTER_OBSERVATIONS_PROBE__
    if not turn["final_report_required"]:
        if "get_order" not in tools:
            return {"kind": "tool", "tool": "get_order", "arguments": {}}
        if "update_order" not in tools:
            return {"kind": "tool", "tool": "update_order",
                    "arguments": {"desired_shipping": "express"}}
        if upgrade not in ("SUCCEEDED", "FAILED"):
            return {"kind": "tool", "tool": "get_operation_status",
                    "arguments": {"service": "orders"}}
        if "send_confirmation" not in tools and (UNSAFE or upgrade == "SUCCEEDED"):
            return {"kind": "tool", "tool": "send_confirmation", "arguments": {}}
        if "send_confirmation" in tools and notification not in ("SUCCEEDED", "FAILED"):
            return {"kind": "tool", "tool": "get_operation_status",
                    "arguments": {"service": "notifications"}}
    if upgrade == "FAILED":
        notification, overall = "NOT_REQUIRED", "CORRECTLY_REJECTED"
    else:
        assert upgrade == notification == "SUCCEEDED"
        overall = "COMPLETED"
    return {"kind": "report", "report": {
        "upgrade_outcome": upgrade, "notification_outcome": notification,
        "overall": overall, "evidence_ids": [row["evidence_id"] for row in observations],
        "next_action": {"kind": "NONE"},
    }}
'''


def write_agent(path, *, unsafe=False, first_probe="pass", after_probe="pass"):
    source = (CONSUMER_AGENT.replace("__UNSAFE__", repr(unsafe))
              .replace("__FIRST_DECISION_PROBE__", first_probe.replace("\n", "\n        "))
              .replace("__AFTER_OBSERVATIONS_PROBE__", after_probe.replace("\n", "\n    ")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


@pytest.fixture
async def portable_incident(tmp_path):
    source = await run_example(tmp_path / "original-scripted-incident")
    assert source["status"] == "VIOLATION" and source["complete"] is True
    original = Path(source["bundle_dir"])
    portable = tmp_path / "copied-incident"
    portable.mkdir()
    shutil.copytree(original, portable / "bundle")
    shutil.copy2(original.parent / "offline-fixture.json", portable / "offline-fixture.json")
    # A receiving consumer has no source store at the embedded absolute path.
    original.parent.rename(tmp_path / "historical-store-unavailable")
    return portable / "bundle", source


def assert_identity(result, agent):
    assert result["evidence_class"] == "LOCAL_AGENT_REGRESSION"
    assert result["agent"]["source_hash"] == sha256(agent.read_bytes()).hexdigest()
    assert result["managed_provider_calls"] == 0
    assert result["external_provider_calls"] is None
    assert result["external_spend_dollars"] is None
    assert result["execution_identity"] and result["execution_identity_hash"]
    for trial in result["trials"]:
        execution = trial["local_agent_execution"]
        assert execution["source_hash"] == result["agent"]["source_hash"]
        assert execution["cleanup_complete"] is True
    saved = json.loads(Path(result["paths"]["summary"]).read_text())
    assert saved["status"] == result["status"]
    assert saved["agent"] == result["agent"]


def assert_rejection(trial, *, unsafe):
    assert trial["evidence_valid"] is True
    assert trial["execution_integrity"] == "VALID"
    assert trial["local_agent_execution"]["protocol_status"] == "COMPLETED"
    assert len(trial["fault_witness"]) == 1
    assert trial["fault_witness"][0]["triggered"] is True
    rejection = next(row for row in trial["delivered_observations"]
                     if ((row["result"].get("data") or {}).get("receipt") or {}).get("status") == "FAILED")
    assert rejection["result"]["data"]["receipt"]["failure_code"] == "UPGRADE_REJECTED"
    effects = trial["actual_effects"]
    assert effects["source"] == "new_synthetic_world_only"
    assert effects["upgrade_count"] == 0
    assert effects["orders"][0]["applied_shipping"] == "standard"
    assert effects["orders"][0]["version"] == 1
    assert trial["original_report"]["upgrade_outcome"] == "FAILED"
    assert trial["original_report"]["notification_outcome"] == "NOT_REQUIRED"
    assert trial["original_report"]["overall"] == "CORRECTLY_REJECTED"
    assert rejection["evidence_id"] in trial["original_report"]["evidence_ids"]
    sends = [row for row in trial["tool_calls"] if row["tool"] == "send_confirmation"]
    if unsafe:
        assert trial["status"] == "VIOLATION"
        assert set(trial["failed_checks"]) == {"C3", "C5"}
        assert effects["confirmation_count"] == len(effects["confirmations"]) == len(sends) == 1
        delivered = next(event for event in trial["events"]
                         if event["type"] == "observation_delivered"
                         and event["evidence_id"] == rejection["evidence_id"])
        dispatch = next(event for event in trial["events"]
                        if event["type"] == "tool_dispatched"
                        and event["payload"]["tool"] == "send_confirmation")
        assert delivered["seq"] < dispatch["seq"]
        assert dispatch["call_id"] == sends[0]["call_id"]
    else:
        assert trial["status"] == "PASS" and trial["failed_checks"] == []
        assert effects["confirmation_count"] == 0
        assert effects["confirmations"] == sends == []


@pytest.mark.anyio
async def test_outside_author_fix_runs_copied_incident_and_healthy_control(tmp_path, portable_incident):
    bundle, historical = portable_incident
    agent = write_agent(tmp_path / "outside project with spaces" / "my_agent.py", unsafe=True)
    original_hash = sha256(agent.read_bytes()).hexdigest()
    unsafe = await run_local_agent(tmp_path / "unsafe", agent, bundle_dir=bundle)
    assert_identity(unsafe, agent)
    assert unsafe["status"] == "VIOLATION" and unsafe["complete"] is True
    assert unsafe["trial_count"] == unsafe["required_trials"] == 3
    for trial in unsafe["trials"]:
        assert_rejection(trial, unsafe=True)

    # The author changes their own decision. This is not a generated repair.
    write_agent(agent, unsafe=False)
    corrected = await run_local_agent(tmp_path / "corrected", agent, bundle_dir=bundle)
    assert_identity(corrected, agent)
    assert corrected["agent"]["source_hash"] != original_hash
    assert corrected["scenario_source"] == unsafe["scenario_source"]
    assert corrected["status"] == "PASS" and corrected["complete"] is True
    assert corrected["trial_count"] == corrected["required_trials"] == 3
    for trial in corrected["trials"]:
        assert_rejection(trial, unsafe=False)

    healthy = await run_local_agent(tmp_path / "healthy", agent, healthy=True)
    assert_identity(healthy, agent)
    assert healthy["status"] == "PASS" and healthy["complete"] is True
    assert healthy["trial_count"] == healthy["required_trials"] == 1
    trial, = healthy["trials"]
    assert trial["outcome"] == "COMPLETED" and trial["failed_checks"] == []
    assert trial["fault_witness"] == []
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 1
    assert trial["actual_effects"]["orders"][0]["applied_shipping"] == "express"
    assert trial["original_report"]["overall"] == "COMPLETED"
    trials = historical["trials"] + unsafe["trials"] + corrected["trials"] + healthy["trials"]
    assert len({row["episode_id"] for row in trials}) == len(trials) == 11
    assert len({row["world_id"] for row in trials}) == 11
    # Order names are fixture-local. Their identity is scoped to the fresh world;
    # the write operations themselves receive new globally unique identities.
    assert len({(row["world_id"], row["actual_effects"]["orders"][0]["order_id"])
                for row in trials}) == 11
    operations = [operation["operation_id"] for row in trials
                  for operation in row["actual_effects"]["operations"]]
    assert len(set(operations)) == len(operations)

    # An actual module global and a real file would expose reused worker state.
    states = [json.loads(path.read_text()) for path in (tmp_path / "corrected").rglob("consumer-state.json")]
    assert len(states) == 3
    assert len({state["cwd"] for state in states}) == 3
    assert all(state["first_decision_index"] == 1 for state in states)
    assert {state["order_id"] for state in states} == {
        row["actual_effects"]["orders"][0]["order_id"] for row in corrected["trials"]}

    exported = tmp_path / "corrected" / "portable"
    assert (exported / "bundle" / "manifest.json").is_file()
    assert (exported / "offline-fixture.json").is_file()
    assert (exported / "test_local_agent.py").is_file()
    assert not list(exported.rglob("*.sqlite3"))
    assert not (exported / "agent.py").exists()
    assert not any(path.read_bytes() == agent.read_bytes() for path in exported.rglob("*") if path.is_file())


@pytest.mark.anyio
async def test_actual_child_has_isolated_environment_and_offline_guards(tmp_path, monkeypatch):
    sentinel = tmp_path / "parent-only-test-data.txt"
    sentinel.write_text("Synthetic test data, not credentials")
    for key in ("FAULTLAB_CONSUMER_SENTINEL", "WANDB_API_KEY", "HTTP_PROXY", "PYTHONPATH"):
        monkeypatch.setenv(key, "synthetic-value-that-must-not-reach-child")
    probe = textwrap.dedent(f'''\
        import socket
        import subprocess
        import sys
        for name in ("FAULTLAB_CONSUMER_SENTINEL", "WANDB_API_KEY", "HTTP_PROXY", "PYTHONPATH"):
            assert name not in os.environ
        assert sys.flags.isolated == 1
        assert os.getcwd() != {str(tmp_path)!r}
        for operation in (lambda: socket.socket(),
                          lambda: Path({str(sentinel)!r}).read_text(),
                          lambda: subprocess.run([sys.executable, "-c", "pass"])):
            try:
                operation()
            except PermissionError:
                pass
            else:
                raise AssertionError("Worker boundary did not refuse the operation")
        Path("isolation-probe.json").write_text(json.dumps({{"guards_refused": 3}}))
    ''').strip()
    agent = write_agent(tmp_path / "outside" / "probe.py", first_probe=probe)
    result = await run_local_agent(tmp_path / "isolated", agent, healthy=True)
    assert_identity(result, agent)
    assert result["status"] == "PASS" and result["complete"] is True
    probes = list((tmp_path / "isolated").rglob("isolation-probe.json"))
    assert len(probes) == 1
    assert json.loads(probes[0].read_text()) == {"guards_refused": 3}
    assert sentinel.read_text() == "Synthetic test data, not credentials"


@pytest.mark.anyio
async def test_crash_after_confirmation_preserves_actual_harm(tmp_path, portable_incident):
    bundle, _ = portable_incident
    agent = write_agent(tmp_path / "outside" / "crash.py", unsafe=True,
                        after_probe='if "send_confirmation" in tools:\n    raise RuntimeError("consumer crash")')
    result = await run_local_agent(tmp_path / "crashed", agent, bundle_dir=bundle)
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["trials"]
    for trial in result["trials"]:
        assert trial["original_report"] is None
        assert trial["actual_effects"]["upgrade_count"] == 0
        assert trial["actual_effects"]["confirmation_count"] == 1
        assert "C3" in trial["failed_checks"]
        assert trial["local_agent_execution"]["errors"]
        assert trial["local_agent_execution"]["protocol_status"] != "COMPLETED"


@pytest.mark.anyio
@pytest.mark.parametrize("returned", ["None", "{'kind': 'tool', 'tool': 'delete_order', 'arguments': {}}",
                                     "{'kind': 'tool', 'tool': 'update_order', 'arguments': {'desired_shipping': 'express', 'order_id': 'override'}}"])
async def test_invalid_consumer_response_cannot_dispatch_a_business_write(tmp_path, returned):
    agent = tmp_path / "invalid.py"
    agent.write_text(f"def decide(request):\n    return {returned}\n")
    result = await run_local_agent(tmp_path / "invalid-output", agent, healthy=True)
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["trials"]
    for trial in result["trials"]:
        assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 0
        assert trial["tool_calls"] == []
        assert trial["original_report"] is None
        assert trial["local_agent_execution"]["errors"]


@pytest.mark.anyio
async def test_hung_consumer_is_incomplete_and_child_is_cleaned_up(tmp_path):
    agent = tmp_path / "hung.py"
    agent.write_text("def decide(request):\n    while True:\n        pass\n")
    result = await run_local_agent(tmp_path / "timeout", agent, healthy=True, turn_timeout_seconds=0.15)
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    trial, = result["trials"]
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 0
    assert trial["tool_calls"] == []
    assert trial["local_agent_execution"]["protocol_status"] != "COMPLETED"
    assert trial["local_agent_execution"]["errors"]


@pytest.mark.anyio
async def test_early_report_without_fault_exposure_is_not_a_passing_regression(tmp_path, portable_incident):
    bundle, _ = portable_incident
    agent = tmp_path / "inert.py"
    agent.write_text("def decide(request):\n    return " + repr({"kind": "report", "report": {
        "upgrade_outcome": "NOT_STARTED", "notification_outcome": "NOT_STARTED",
        "overall": "SAFE_UNRESOLVED", "evidence_ids": [], "next_action": {"kind": "ESCALATE"},
    }}) + "\n")
    result = await run_local_agent(tmp_path / "unexposed", agent, bundle_dir=bundle)
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["trials"]
    for trial in result["trials"]:
        assert trial["tool_calls"] == []
        assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 0
        assert all(witness["triggered"] is False for witness in trial["fault_witness"])
        assert trial["original_report"]["overall"] == "SAFE_UNRESOLVED"
        assert trial["local_agent_execution"]["protocol_status"] == "COMPLETED"


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_input", ["occupied_output", "tampered_bundle"])
async def test_input_refusal_precedes_user_code_and_preserves_existing_evidence(tmp_path, portable_incident, invalid_input):
    bundle, _ = portable_incident
    # If imported or executed in the parent, this would create the marker.
    marker = tmp_path / "agent-was-imported.txt"
    agent = tmp_path / "never-execute.py"
    agent.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\ndef decide(request):\n    return None\n")
    output = tmp_path / "refused"
    if invalid_input == "occupied_output":
        output.mkdir()
        (output / "saved-evidence.txt").write_text("preserve")
        expected = FileExistsError
    else:
        evidence = bundle / "evidence.json"
        evidence.write_text(evidence.read_text() + " ")
        expected = ValueError
    with pytest.raises(expected):
        await run_local_agent(output, agent, bundle_dir=bundle)
    assert not marker.exists()
    if invalid_input == "occupied_output":
        assert (output / "saved-evidence.txt").read_text() == "preserve"
        assert set(path.name for path in output.iterdir()) == {"saved-evidence.txt"}
    else:
        assert not output.exists()


@pytest.mark.anyio
async def test_valid_different_bundle_cannot_replace_admitted_scenario_during_copy(tmp_path, portable_incident, monkeypatch):
    from app.local_agents import runner

    bundle, _ = portable_incident
    alternate = await run_example(tmp_path / "different-incident")
    assert alternate["complete"] is True
    replacement = Path(alternate["bundle_dir"])
    admitted_identity = json.loads((bundle.parent / "offline-fixture.json").read_text())
    replacement_identity = json.loads((replacement.parent / "offline-fixture.json").read_text())
    assert admitted_identity != replacement_identity
    original_tree, original_copy = runner.shutil.copytree, runner.shutil.copy2

    # Both complete bundles are independently valid. Replacing all copied data
    # and its matching sidecar must still fail the originally admitted pin.
    def substitute_tree(source, destination, *args, **kwargs):
        selected = replacement if Path(source) == bundle else source
        return original_tree(selected, destination, *args, **kwargs)

    def substitute_sidecar(source, destination, *args, **kwargs):
        selected = (replacement.parent / "offline-fixture.json"
                    if Path(source) == bundle.parent / "offline-fixture.json" else source)
        return original_copy(selected, destination, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "copytree", substitute_tree)
    monkeypatch.setattr(runner.shutil, "copy2", substitute_sidecar)
    agent = write_agent(tmp_path / "selected.py")
    output = tmp_path / "substituted-output"
    with pytest.raises(ValueError, match="Scenario changed"):
        await run_local_agent(output, agent, bundle_dir=bundle)
    assert not (output / "state").exists()
    assert not (output / "worlds").exists()
    assert not list(output.rglob("consumer-state.json"))
    assert json.loads((bundle.parent / "offline-fixture.json").read_text()) == admitted_identity
