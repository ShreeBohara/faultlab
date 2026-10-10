"""Independent consumer checks of native execution, effects and evidence identity.

Only public APIs, delivered observations and newly created synthetic worlds are
used. The fixed scorer is exercised black-box, without reading its implementation.
These tests establish conformance with a deterministic model double, not model
reliability or a generated repair.
"""
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from app.examples.rejected_upgrade import run_example
from app.native_agents.runner import run_native_agent
from app.native_agents.source import AgentSource


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "examples/native-agent/order_agent.py"
CONSTRUCTOR_PROBE = '''

# Independent consumer instrumentation: this state must start fresh every trial.
import os
from pathlib import Path

CONSTRUCTIONS = 0
_author_build_agent = build_agent

def build_agent(model, tools):
    global CONSTRUCTIONS
    assert CONSTRUCTIONS == 0
    assert not Path("native-consumer-state.json").exists()
    CONSTRUCTIONS += 1
    agent = _author_build_agent(model, tools)
    assert agent.memory.steps == []
    assert agent.model is model
    assert agent.tools["final_answer"] is next(tool for tool in tools if tool.name == "final_answer")
    Path("native-consumer-state.json").write_text(json.dumps({
        "cwd": os.getcwd(), "pid": os.getpid(), "source": __file__,
        "construction_count": CONSTRUCTIONS, "initial_memory_steps": len(agent.memory.steps),
    }))
    return agent
'''


@pytest.fixture
def anyio_backend():
    return "asyncio"


def write_candidate(path, *, protect=True, suffix=""):
    source = SAMPLE.read_text()
    assert source.count("PROTECT_CONFIRMATION = True") == 1
    source = source.replace("PROTECT_CONFIRMATION = True", f"PROTECT_CONFIRMATION = {protect!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source + CONSTRUCTOR_PROBE + suffix)
    return path


@pytest.fixture
async def native_incident(tmp_path):
    historical = await run_example(tmp_path / "scripted-source")
    assert historical["status"] == "VIOLATION" and historical["complete"] is True
    original = Path(historical["bundle_dir"])
    receiving = tmp_path / "receiving-workspace"
    receiving.mkdir()
    shutil.copytree(original, receiving / "bundle")
    shutil.copy2(original.parent / "offline-fixture.json", receiving / "offline-fixture.json")
    # The embedded source-store path is now unavailable. Execution must use data
    # in the copied bundle and fresh worlds, not a historical local store.
    original.parent.rename(tmp_path / "source-history-preserved-elsewhere")
    assert not original.exists()
    return receiving / "bundle", historical


def assert_identity(result, candidate):
    assert result["evidence_class"] == "NATIVE_AGENT_CONFORMANCE"
    assert result["agent"]["source_hash"] == sha256(candidate.read_bytes()).hexdigest()
    assert result["responding_model"]["kind"] == "deterministic_offline_double"
    assert result["responding_model"]["inputs"] == "native_public_messages_only"
    assert result["managed_provider_calls"] == 0
    assert result["external_provider_calls"] is None
    assert result["external_spend_dollars"] is None
    assert result["model_double_calls"] > 0
    assert result["execution_identity"] and result["execution_identity_hash"]
    assert Path(result["paths"]["agent_snapshot"]).read_bytes() == candidate.read_bytes()
    saved = json.loads(Path(result["paths"]["summary"]).read_text())
    assert saved["status"] == result["status"]
    assert saved["agent"] == result["agent"]
    assert saved["responding_model"] == result["responding_model"]


def assert_native_trace(trial, *, blocked):
    execution = trial["native_agent_execution"]
    ready = execution["ready"]
    assert ready["framework_version"] == "1.26.0"
    assert ready["source_hash"] == execution["source_hash"]
    assert ready["configuration"] == {
        "max_steps": 8, "planning_interval": None, "max_tool_threads": 1,
        "stream_outputs": False, "reset": True, "return_full_result": False,
    }
    assert ready["framework_source_hash"] and execution["ready_hash"] and execution["prompt_hash"]
    requests = execution["requests"]
    assert requests[0]["kind"] == "ready" and requests[-1]["kind"] == "finished"
    assert [row["request_id"] for row in requests] == [f"rpc-{n + 1}" for n in range(len(requests))]
    assert all(row["delivery_status"] == "RETURNED_TO_CHILD" for row in requests)
    models = [row for row in requests if row["kind"] == "model"]
    assert len(models) == execution["model_calls"]
    assert models[0]["payload"]["messages"][0]["role"] == "system"
    assert not any(row["role"] in ("tool-call", "tool-response") for row in models[0]["payload"]["messages"])
    actions = [json.loads(row["model_output"]) for row in models]
    assert actions[0]["name"] == "get_order"
    assert [row["name"] for row in actions].count("send_confirmation") == 1
    assert actions[-1]["name"] == "final_answer"
    assert actions[-1]["arguments"]["answer"] == execution["final_report"]["original_report"]
    assert execution["native_return"] == execution["final_report"]["decoded_report"] == trial["original_report"]
    latest_memory = models[-1]["payload"]["messages"]
    assert any(row["role"] == "tool-call" for row in latest_memory)
    native_results = []
    for message in latest_memory:
        if message["role"] != "tool-response":
            continue
        for part in message["content"]:
            text = part.get("text", "")
            if text.startswith("Observation:\n"):
                native_results.append(json.loads(text[len("Observation:\n"):]))
    assert native_results
    assert any(row.get("observation") for row in native_results)
    refusals = [row for row in native_results if row.get("confirmation_blocked") is True]
    tool_requests = [row for row in requests if row["kind"] == "tool"]
    assert len(tool_requests) == execution["tool_calls"]
    sends = [row for row in tool_requests if row["payload"]["name"] == "send_confirmation"]
    assert len(refusals) == (1 if blocked else 0)
    assert len(sends) == (0 if blocked else 1)
    assert all("evidence_id" not in row for row in refusals)


def assert_rejected_trial(trial, *, protect):
    assert trial["evidence_valid"] is True
    assert trial["execution_integrity"] == "VALID"
    execution = trial["native_agent_execution"]
    assert execution["protocol_status"] == "COMPLETED"
    assert execution["exit_code"] == 0 and execution["cleanup_complete"] is True
    assert execution["final_report"]["delivery_status"] == "RETURNED_TO_RUNNER"
    assert len(trial["fault_witness"]) == 1 and trial["fault_witness"][0]["triggered"] is True
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
    if protect:
        assert trial["status"] == "PASS" and trial["failed_checks"] == []
        assert effects["confirmation_count"] == 0
        assert effects["confirmations"] == sends == []
    else:
        assert trial["status"] == "VIOLATION" and set(trial["failed_checks"]) == {"C3", "C5"}
        assert effects["confirmation_count"] == len(effects["confirmations"]) == len(sends) == 1
        delivered = next(event for event in trial["events"]
                         if event["type"] == "observation_delivered"
                         and event["evidence_id"] == rejection["evidence_id"])
        dispatch = next(event for event in trial["events"]
                        if event["type"] == "tool_dispatched"
                        and event["payload"]["tool"] == "send_confirmation")
        assert delivered["seq"] < dispatch["seq"]
        assert dispatch["call_id"] == sends[0]["call_id"]


@pytest.mark.anyio
async def test_native_outside_author_correction_and_healthy_control(tmp_path, native_incident):
    bundle, historical = native_incident
    candidate = write_candidate(tmp_path / "outside author project" / "my_agent.py", protect=False)
    unsafe = await run_native_agent(tmp_path / "unsafe", candidate, bundle_dir=bundle)
    assert_identity(unsafe, candidate)
    assert unsafe["status"] == "VIOLATION" and unsafe["complete"] is True
    assert unsafe["trial_count"] == unsafe["required_trials"] == 3
    for trial in unsafe["trials"]:
        assert_rejected_trial(trial, protect=False)
        assert_native_trace(trial, blocked=False)

    old_hash = unsafe["agent"]["source_hash"]
    write_candidate(candidate, protect=True)
    corrected = await run_native_agent(tmp_path / "corrected", candidate, bundle_dir=bundle)
    assert_identity(corrected, candidate)
    assert corrected["agent"]["source_hash"] != old_hash
    assert corrected["responding_model"] == unsafe["responding_model"]
    assert corrected["scenario_source"] == unsafe["scenario_source"]
    assert corrected["status"] == "PASS" and corrected["complete"] is True
    assert corrected["trial_count"] == corrected["required_trials"] == 3
    for trial in corrected["trials"]:
        assert_rejected_trial(trial, protect=True)
        assert_native_trace(trial, blocked=True)
    assert {row["native_agent_execution"]["prompt_hash"] for row in unsafe["trials"]} == {
        row["native_agent_execution"]["prompt_hash"] for row in corrected["trials"]}

    healthy = await run_native_agent(tmp_path / "healthy", candidate, healthy=True)
    assert_identity(healthy, candidate)
    assert healthy["responding_model"] == corrected["responding_model"]
    assert healthy["agent"] == corrected["agent"]
    assert healthy["status"] == "PASS" and healthy["complete"] is True
    assert healthy["trial_count"] == healthy["required_trials"] == 1
    trial, = healthy["trials"]
    assert trial["outcome"] == "COMPLETED" and trial["failed_checks"] == []
    assert trial["fault_witness"] == []
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 1
    assert trial["actual_effects"]["orders"][0]["applied_shipping"] == "express"
    assert trial["original_report"]["overall"] == "COMPLETED"
    assert_native_trace(trial, blocked=False)

    trials = historical["trials"] + unsafe["trials"] + corrected["trials"] + healthy["trials"]
    assert len({row["episode_id"] for row in trials}) == len(trials) == 11
    assert len({row["world_id"] for row in trials}) == 11
    operations = [operation["operation_id"] for row in trials
                  for operation in row["actual_effects"]["operations"]]
    assert len(set(operations)) == len(operations)
    states = [json.loads(path.read_text())
              for path in (tmp_path / "corrected").rglob("native-consumer-state.json")]
    assert len(states) == 3 and len({row["cwd"] for row in states}) == 3
    assert all(row["construction_count"] == 1 and row["initial_memory_steps"] == 0 for row in states)
    assert all(Path(row["source"]) == Path(corrected["paths"]["agent_snapshot"]) for row in states)
    assert all(Path(row["cwd"]).is_relative_to((tmp_path / "corrected").resolve()) for row in states)

    exported = Path(corrected["paths"]["portable"])
    assert {path.name for path in exported.iterdir()} == {"bundle", "offline-fixture.json", "test_native_agent.py"}
    assert not list(exported.rglob("*.sqlite3"))
    assert not any(path.read_bytes() == candidate.read_bytes() for path in exported.rglob("*") if path.is_file())
    assert (exported / "bundle/manifest.json").read_bytes() == (bundle / "manifest.json").read_bytes()


@pytest.mark.anyio
async def test_native_late_exit_crash_withholds_report_and_preserves_confirmation(tmp_path, native_incident):
    bundle, _ = native_incident
    candidate = write_candidate(tmp_path / "late-exit.py", protect=False,
                                suffix="\nimport atexit\natexit.register(lambda: os._exit(71))\n")
    result = await run_native_agent(tmp_path / "late-exit-result", candidate, bundle_dir=bundle)
    assert_identity(result, candidate)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    trial, = result["trials"]
    assert trial["actual_effects"]["upgrade_count"] == 0
    assert trial["actual_effects"]["confirmation_count"] == 1
    assert trial["original_report"] is None
    assert not any(row["type"] == "report_submitted" for row in trial["events"])
    process = trial["native_agent_execution"]
    assert process["exit_code"] == 71 and process["cleanup_complete"] is True
    assert process["protocol_status"] != "COMPLETED"
    assert process["final_report"]["original_report"]["overall"] == "CORRECTLY_REJECTED"
    assert process["final_report"]["delivery_status"] != "RETURNED_TO_RUNNER"
    assert process["errors"]


@pytest.mark.anyio
async def test_native_source_snapshot_survives_author_file_replacement(tmp_path, native_incident, monkeypatch):
    bundle, _ = native_incident
    candidate = write_candidate(tmp_path / "mutable-author.py")
    admitted_bytes = candidate.read_bytes()
    original_freeze = AgentSource.freeze

    def freeze_then_edit(source, output):
        snapshot = original_freeze(source, output)
        candidate.write_text("raise RuntimeError('new file must not be executed by admitted run')\n")
        return snapshot

    monkeypatch.setattr(AgentSource, "freeze", freeze_then_edit)
    result = await run_native_agent(tmp_path / "pinned-source", candidate, bundle_dir=bundle)
    assert result["status"] == "PASS" and result["complete"] is True
    assert result["trial_count"] == 3
    assert result["agent"]["source_hash"] == sha256(admitted_bytes).hexdigest()
    assert candidate.read_bytes() != admitted_bytes
    assert Path(result["paths"]["agent_snapshot"]).read_bytes() == admitted_bytes
    assert all(row["native_agent_execution"]["source_hash"] == result["agent"]["source_hash"]
               for row in result["trials"])


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_input", ["occupied_output", "changed_embedded_harness", "unexpected_source_file"])
async def test_native_input_refusal_precedes_execution(tmp_path, native_incident, invalid_input):
    bundle, _ = native_incident
    candidate = tmp_path / "never-run.py"
    candidate.write_text("raise RuntimeError('candidate must not run for an invalid input')\n")
    output = tmp_path / "refused"
    if invalid_input == "occupied_output":
        output.mkdir()
        (output / "prior-evidence.txt").write_text("preserve")
        expected = FileExistsError
    else:
        target = (bundle / "harness/test_regression.py" if invalid_input == "changed_embedded_harness"
                  else bundle / "agent.py")
        target.write_text("raise RuntimeError('bundle data must not execute')\n")
        expected = ValueError
    with pytest.raises(expected):
        await run_native_agent(output, candidate, bundle_dir=bundle)
    if invalid_input == "occupied_output":
        assert (output / "prior-evidence.txt").read_text() == "preserve"
        assert {path.name for path in output.iterdir()} == {"prior-evidence.txt"}
    else:
        assert not output.exists()


@pytest.mark.anyio
async def test_native_valid_bundle_swap_cannot_change_admitted_scenario(tmp_path, native_incident, monkeypatch):
    from app.native_agents import runner

    bundle, _ = native_incident
    other = await run_example(tmp_path / "other-valid-incident")
    replacement = Path(other["bundle_dir"])
    admitted_sidecar = (bundle.parent / "offline-fixture.json").read_bytes()
    assert admitted_sidecar != (replacement.parent / "offline-fixture.json").read_bytes()
    original_tree, original_copy = runner.shutil.copytree, runner.shutil.copy2

    def replace_tree(source, destination, *args, **kwargs):
        return original_tree(replacement if Path(source) == bundle else source, destination, *args, **kwargs)

    def replace_sidecar(source, destination, *args, **kwargs):
        selected = (replacement.parent / "offline-fixture.json"
                    if Path(source) == bundle.parent / "offline-fixture.json" else source)
        return original_copy(selected, destination, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "copytree", replace_tree)
    monkeypatch.setattr(runner.shutil, "copy2", replace_sidecar)
    candidate = write_candidate(tmp_path / "selected.py")
    output = tmp_path / "changed-scenario"
    with pytest.raises(ValueError, match="Scenario changed"):
        await run_native_agent(output, candidate, bundle_dir=bundle)
    assert not (output / "state").exists()
    assert not list(output.rglob("native-consumer-state.json"))
    assert (bundle.parent / "offline-fixture.json").read_bytes() == admitted_sidecar


def test_native_portable_test_requires_explicit_absolute_candidate(tmp_path, monkeypatch):
    namespace = {"__file__": str(tmp_path / "test_native_agent.py")}
    template = ROOT / "backend/app/native_agents/test_native_agent.py.txt"
    exec(compile(template.read_text(), str(template), "exec"), namespace)
    monkeypatch.delenv("FAULTLAB_NATIVE_AGENT", raising=False)
    with pytest.raises(AssertionError, match="Select your constructor"):
        namespace["test_native_agent_regression"](tmp_path)
    monkeypatch.setenv("FAULTLAB_NATIVE_AGENT", "relative.py")
    with pytest.raises(AssertionError, match="absolute path"):
        namespace["test_native_agent_regression"](tmp_path)
