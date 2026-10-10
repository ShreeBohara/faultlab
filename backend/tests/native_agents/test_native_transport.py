"""Real child failures and process ownership for the native framework boundary."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest

from app.native_agents.runner import run_native_agent
from app.native_agents.source import read_agent
from app.native_agents.transport import NativeAgentProvider, valid_execution
from app.contracts.models import canonical_json

SAMPLE = Path(__file__).resolve().parents[3] / "examples/native-agent/order_agent.py"
PRIVATE_MARKER = "NATIVE_CHILD_DIAGNOSTIC_MUST_NOT_ESCAPE"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def authored(path, suffix):
    path.write_text(SAMPLE.read_text() + "\n" + suffix)
    return path


def assert_reaped(record):
    assert record["process_creation_complete"] is True
    assert record["cleanup_complete"] is True
    assert type(record["process_id"]) is int
    assert type(record["exit_code"]) is int
    with pytest.raises(ProcessLookupError):
        os.kill(record["process_id"], 0)


@pytest.mark.anyio
@pytest.mark.parametrize(("suffix", "code"), [
    ("import os\nos.write(1,b'{\"protocol\":\"faultlab-native-agent/v1\",\"request_id\":\"wrong\",\"kind\":\"ready\",\"payload\":{}}\\n')",
     "NATIVE_AGENT_INVALID_ENVELOPE"),
    ("import os\nos.write(1,b'{\"protocol\":\"faultlab-native-agent/v1\",\"request_id\":\"rpc-1\",\"request_id\":\"rpc-1\",\"kind\":\"ready\",\"payload\":{}}\\n')",
     "NATIVE_AGENT_PROTOCOL_ERROR"),
    (f"import sys\nsys.stderr.write({PRIVATE_MARKER!r}+'x'*1048576)\nsys.stderr.flush()",
     "NATIVE_AGENT_STDERR_LIMIT"),
    ("original_build=build_agent\ndef build_agent(model,tools):\n    agent=original_build(model,tools)\n    agent.instructions='x'*70000\n    return agent",
     "NATIVE_AGENT_EOF"),
    ("def build_agent(model,tools):\n    return {}", "NATIVE_AGENT_EOF"),
    ("original_build=build_agent\ndef build_agent(model,tools):\n    model.generate=lambda *a,**k: None\n    return original_build(model,tools)",
     "NATIVE_AGENT_EOF"),
    ("original_build=build_agent\ndef build_agent(model,tools):\n    try:\n        tools[0]()\n    except PermissionError:\n        pass\n    return original_build(model,tools)",
     "NATIVE_AGENT_EOF"),
    ("build_agent=None", "NATIVE_AGENT_EOF"),
    ("def build_agent(model,tools):\n    while True:\n        pass", "NATIVE_AGENT_TIMEOUT"),
])
async def test_native_child_protocol_failures_cannot_pass(tmp_path, suffix, code):
    source = authored(tmp_path / "outside-agent.py", suffix)
    result = await asyncio.wait_for(run_native_agent(tmp_path / "output", source,
                                                    healthy=True, turn_timeout_seconds=1.5), timeout=9)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["model_double_calls"] == 0
    trial, = result["trials"]
    record = trial["native_agent_execution"]
    assert code in record["errors"]
    assert record["protocol_status"] == "FAILED"
    assert trial["original_report"] is None
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 0
    assert_reaped(record)
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.anyio
async def test_native_user_code_has_no_inherited_environment_or_outside_capability(tmp_path, monkeypatch):
    monkeypatch.setenv("FAULTLAB_NATIVE_SENTINEL", "should-not-be-inherited")
    monkeypatch.setenv("HTTP_PROXY", "http://example.invalid")
    monkeypatch.setenv("PYTHONPATH", "must-not-be-inherited")
    sentinel = tmp_path / "public-sentinel.txt"
    sentinel.write_text("non-secret sentinel")
    suffix = f"""
import json, os, socket, subprocess
from pathlib import Path
results={{'environment': {{key:os.getenv(key) for key in ('FAULTLAB_NATIVE_SENTINEL','HTTP_PROXY','PYTHONPATH')}}}}
for name,fn in [('outside_read',lambda:Path({str(sentinel)!r}).read_text()),
                ('network',lambda:socket.socket()),
                ('subprocess',lambda:subprocess.run(['true']))]:
    try:
        fn()
        results[name]='unexpected success'
    except PermissionError:
        results[name]='refused'
Path('guard-probe.json').write_text(json.dumps(results))
"""
    source = authored(tmp_path / "outside-agent.py", suffix)
    result = await run_native_agent(tmp_path / "output", source, healthy=True)
    assert result["status"] == "PASS"
    trial, = result["trials"]
    record = trial["native_agent_execution"]
    assert_reaped(record)
    probe = json.loads((tmp_path / "output" / "agent-work" / record["episode_id"] / "guard-probe.json").read_text())
    assert probe == {"environment": {"FAULTLAB_NATIVE_SENTINEL": None, "HTTP_PROXY": None, "PYTHONPATH": None},
                     "outside_read": "refused", "network": "refused", "subprocess": "refused"}
    snapshot = SimpleNamespace(source_hash=record["source_hash"])
    assert valid_execution(record, snapshot, record["identity"])
    assert valid_execution(json.loads(canonical_json(record)), snapshot, record["identity"])
    reordered = deepcopy(record)
    event = reordered["final_report"]["submission_event"]
    event["evidence_labels"] = dict(sorted(event["evidence_labels"].items(), key=lambda item: item[1], reverse=True))
    assert valid_execution(reordered, snapshot, record["identity"])
    for mutation in ("null_request", "ready_hash", "prompt_hash", "native_report", "boolean_identity"):
        broken = deepcopy(record)
        if mutation == "null_request":
            broken["requests"][0] = None
        elif mutation == "ready_hash":
            broken["ready"]["framework_source_hash"] = "0" * 64
        elif mutation == "prompt_hash":
            broken["ready"]["prompt"]["instructions"] = "mutated"
        elif mutation == "boolean_identity":
            broken["identity"]["managed_provider_calls"] = False
        else:
            broken["native_return"]["evidence_ids"] = []
        assert valid_execution(broken, snapshot, record["identity"]) is False
    # Changing all final report copies together must still fail when the model
    # and native tool request actually supplied a different report.
    broken = deepcopy(record)
    original = {**broken["final_report"]["original_report"], "overall": "SAFE_UNRESOLVED",
                "next_action": {"kind": "ESCALATE"}}
    decoded = {**broken["final_report"]["decoded_report"], "overall": "SAFE_UNRESOLVED",
               "next_action": {"kind": "ESCALATE"}}
    broken["final_report"]["original_report"] = original
    broken["final_report"]["decoded_report"] = decoded
    broken["final_report"]["submission_event"]["report"] = decoded
    broken["native_return"] = decoded
    broken["requests"][-1]["payload"]["report"] = decoded
    assert valid_execution(broken, snapshot, record["identity"]) is False
    # Even making the final tool RPC and its frame hashes agree does not change
    # what the last model generation actually proposed.
    final_request = broken["requests"][-2]
    final_request["payload"]["arguments"]["answer"] = original
    final_request["tool_result"] = decoded
    for request in (final_request, broken["requests"][-1]):
        raw = canonical_json({"protocol": "faultlab-native-agent/v1", "request_id": request["request_id"],
                              "kind": request["kind"], "payload": request["payload"]}).encode() + b"\n"
        request.update(request_sha256=sha256(raw).hexdigest(), request_bytes=len(raw))
    response = canonical_json({"protocol": "faultlab-native-agent/v1", "request_id": final_request["request_id"],
                               "kind": "result", "payload": decoded}).encode() + b"\n"
    final_request.update(response_sha256=sha256(response).hexdigest(), response_bytes=len(response))
    assert valid_execution(broken, snapshot, record["identity"]) is False


@pytest.mark.anyio
async def test_native_worker_disables_both_dotenv_loaders_for_user_constructor(tmp_path, monkeypatch):
    key = "FAULTLAB_HARMLESS_NATIVE_DOTENV_SENTINEL"
    monkeypatch.delenv(key, raising=False)
    suffix = f"""
original_build = build_agent
def build_agent(model, tools):
    import dotenv
    import dotenv.main
    import json, os
    from pathlib import Path
    sentinel = Path('dotenv-sentinel.txt')
    sentinel.write_text({key!r} + '=harmless-test-value\\n')
    result = {{'public_loader': dotenv.load_dotenv(dotenv_path=sentinel),
               'module_loader': dotenv.main.load_dotenv(dotenv_path=sentinel),
               'environment_value': os.environ.get({key!r})}}
    Path('dotenv-loader-result.json').write_text(json.dumps(result))
    return original_build(model, tools)
"""
    source = authored(tmp_path / "outside-agent.py", suffix)
    result = await run_native_agent(tmp_path / "output", source, healthy=True)
    assert result["status"] == "PASS"
    trial, = result["trials"]
    record = trial["native_agent_execution"]
    assert_reaped(record)
    working = tmp_path / "output" / "agent-work" / record["episode_id"]
    assert (working / "dotenv-sentinel.txt").read_text() == key + "=harmless-test-value\n"
    assert json.loads((working / "dotenv-loader-result.json").read_text()) == {
        "public_loader": False, "module_loader": False, "environment_value": None}
    assert key not in os.environ


@pytest.mark.anyio
async def test_native_double_cancel_during_spawn_retains_and_reaps_child(tmp_path, monkeypatch):
    selected = authored(tmp_path / "outside-agent.py", "")
    output = tmp_path / "output"
    output.mkdir()
    snapshot = read_agent(selected).freeze(output)
    provider = NativeAgentProvider(snapshot, output / "workers", turn_timeout_seconds=5)
    original_spawn = asyncio.create_subprocess_exec
    created, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def delayed_spawn(*args, **kwargs):
        child = await original_spawn(*args, **kwargs)
        processes.append(child)
        created.set()
        await release.wait()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    # The two cancellations land before _start can bind its real child. No
    # simulator, model, or fabricated observation is involved in this probe.
    context = SimpleNamespace(provenance=SimpleNamespace(episode_id="double-cancel"))
    existing_tasks = set(asyncio.all_tasks())
    task = asyncio.create_task(provider.execute({}, context))
    try:
        await asyncio.wait_for(created.wait(), 3)
        task.cancel()
        await asyncio.sleep(0.03)
        task.cancel()
        await asyncio.sleep(0.03)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        record = provider.records["double-cancel"]
        assert record["process_id"] == processes[0].pid
        assert "NATIVE_AGENT_CANCELLED" in record["errors"]
        assert record["report_completed"] is False
        assert_reaped(record)
        assert not [pending for pending in asyncio.all_tasks() if pending not in existing_tasks and not pending.done()]
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for child in processes:
            if child.returncode is None:
                os.killpg(child.pid, signal.SIGKILL)
            await child.wait()
