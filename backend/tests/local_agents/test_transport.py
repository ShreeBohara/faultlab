"""Real subprocess failures cannot become successful or silently retried runs."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import signal

import pytest

from app.local_agents.runner import run_local_agent
from app.local_agents.runner import _valid_process
from app.local_agents.source import read_agent
from app.local_agents.transport import LocalAgentProvider
from test_consumer import assert_identity, write_agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


PRIVATE_MARKER = "CONSUMER_DIAGNOSTIC_MUST_NOT_ENTER_SUMMARY"
REPORT = {"kind": "report", "report": {
    "upgrade_outcome": "NOT_STARTED", "notification_outcome": "NOT_STARTED",
    "overall": "SAFE_UNRESOLVED", "evidence_ids": [], "next_action": {"kind": "ESCALATE"},
}}


def write_failure_agent(path, case):
    body = {
        "stderr_flood": (
            f"import sys\nsys.stderr.write({PRIVATE_MARKER!r} + 'x' * 1048576)\n"
            "sys.stderr.flush()\nreturn action"
        ),
        "oversized_action": "action['report']['evidence_ids'] = ['x' * 70000]\nreturn action",
        "nonfinite_action": "action['report']['evidence_ids'] = [float('nan')]\nreturn action",
        "wrong_request_id": (
            "import os, json\n"
            "frame = {'protocol': request['protocol'], "
            f"'request_id': {PRIVATE_MARKER!r}, 'action': action}}\n"
            "os.write(1, (json.dumps(frame) + '\\n').encode())\nreturn action"
        ),
        "duplicate_json_key": (
            "import os, json\n"
            "identifier = json.dumps(request['request_id'])\n"
            "frame = ('{\"protocol\":\"faultlab-local-action/v1\",\"request_id\":' + identifier "
            "+ ',\"request_id\":' + identifier + ',\"action\":' + json.dumps(action) + '}\\n')\n"
            "os.write(1, frame.encode())\nreturn action"
        ),
    }[case]
    source = "def decide(request):\n    action = " + repr(REPORT) + "\n    " + body.replace("\n", "\n    ") + "\n"
    path.write_text(source)
    return path


def assert_reaped(record):
    assert record["cleanup_complete"] is True
    assert isinstance(record["process_id"], int)
    assert record["exit_code"] is not None
    # The parent has waited for its own child. Merely sending SIGTERM would not
    # suffice: a live or unreaped process can still answer this existence check.
    with pytest.raises(ProcessLookupError):
        os.kill(record["process_id"], 0)


@pytest.mark.anyio
@pytest.mark.parametrize(("case", "error_code"), [
    ("stderr_flood", "LOCAL_AGENT_STDERR_LIMIT"),
    ("oversized_action", "LOCAL_AGENT_EOF"),
    ("nonfinite_action", "LOCAL_AGENT_EOF"),
    ("wrong_request_id", "LOCAL_AGENT_INVALID_ENVELOPE"),
    ("duplicate_json_key", "LOCAL_AGENT_PROTOCOL_ERROR"),
])
async def test_bad_child_output_is_bounded_nonretryable_and_incomplete(tmp_path, case, error_code):
    agent = write_failure_agent(tmp_path / f"{case}.py", case)
    result = await asyncio.wait_for(
        run_local_agent(tmp_path / "result", agent, healthy=True, turn_timeout_seconds=1.0),
        timeout=8.0,
    )
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["decision_calls"] == 1
    trial, = result["trials"]
    assert trial["original_report"] is None
    assert trial["tool_calls"] == []
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 0
    record = trial["local_agent_execution"]
    assert record["protocol_status"] == "FAILED"
    assert error_code in record["errors"]
    assert record["request_count"] == len(record["requests"]) == 1
    assert_reaped(record)
    if case == "stderr_flood":
        assert record["stderr_bytes"] > 65_536
    serialized = json.dumps(result)
    assert PRIVATE_MARKER not in serialized
    assert PRIVATE_MARKER not in Path(result["paths"]["summary"]).read_text()


@pytest.mark.anyio
async def test_valid_report_followed_by_shutdown_crash_is_incomplete(tmp_path):
    probe = ("import atexit\n"
             "def late_crash():\n"
             f"    raise RuntimeError({PRIVATE_MARKER!r})\n"
             "atexit.register(late_crash)")
    agent = write_agent(tmp_path / "late_crash.py", first_probe=probe)
    result = await asyncio.wait_for(
        run_local_agent(tmp_path / "late-result", agent, healthy=True, turn_timeout_seconds=1.0),
        timeout=8.0,
    )
    assert_identity(result, agent)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    trial, = result["trials"]
    # The callback actually completed the business actions before its final
    # response was withheld; a process failure must preserve those effects.
    assert trial["actual_effects"]["upgrade_count"] == trial["actual_effects"]["confirmation_count"] == 1
    assert trial["actual_effects"]["orders"][0]["applied_shipping"] == "express"
    record = trial["local_agent_execution"]
    assert record["protocol_status"] == "FAILED"
    assert record["report_completed"] is False
    assert "LOCAL_AGENT_EXIT_FAILED" in record["errors"]
    final_request = record["requests"][-1]
    assert final_request["action_sha256"]
    assert final_request["delivery_status"] == "WITHHELD"
    assert final_request["validated_action"] == {"kind": "report", "report": {
        "upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED",
        # The callback sees public short labels. A withheld answer must retain
        # them exactly; Actor never received it to decode journal evidence IDs.
        "overall": "COMPLETED", "evidence_ids": [f"obs-{index + 1}" for index in range(len(trial["delivered_observations"]))],
        "next_action": {"kind": "NONE"},
    }}
    assert all(request["delivery_status"] == "RETURNED_TO_ACTOR" for request in record["requests"][:-1])
    assert trial["original_report"] is None
    assert_reaped(record)
    assert PRIVATE_MARKER not in json.dumps(result)


@pytest.mark.anyio
async def test_cancelling_inflight_callback_reaps_the_real_child(tmp_path):
    agent = tmp_path / "cancel.py"
    agent.write_text("from pathlib import Path\ndef decide(request):\n"
                     "    Path('callback-entered.txt').write_text('entered')\n"
                     "    while True:\n        pass\n")
    output = tmp_path / "cancel-output"
    output.mkdir()
    snapshot = read_agent(agent).freeze(output)
    provider = LocalAgentProvider(snapshot, output / "workers", turn_timeout_seconds=5.0)

    async def execute():
        async with provider.episode("cancel-consumer"):
            await provider.complete([{"role": "user", "content": "{}"}])

    task = asyncio.create_task(execute())
    try:
        async with asyncio.timeout(3.0):
            while not (output / "workers" / "cancel-consumer" / "callback-entered.txt").exists():
                if task.done():
                    await task
                    pytest.fail("The callback ended before cancellation")
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3.0)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    record = provider.records["cancel-consumer"]
    assert record["protocol_status"] == "FAILED"
    assert record["report_completed"] is False
    assert record["request_count"] == provider.calls == 1
    assert "LOCAL_AGENT_CANCELLED" in record["errors"]
    assert_reaped(record)


@pytest.mark.anyio
async def test_double_cancellation_during_spawn_adopts_and_reaps_actual_child(tmp_path, monkeypatch):
    """Cancellation must not orphan a real process awaiting its startup handoff.

    Delay only the return of the actual subprocess factory. The test retains its
    own Process reference and unconditionally cleans it up even on a regression.
    """
    agent = tmp_path / "double_cancel.py"
    agent.write_text("def decide(request):\n    while True:\n        pass\n")
    output = tmp_path / "double-cancel-output"
    output.mkdir()
    provider = LocalAgentProvider(read_agent(agent).freeze(output), output / "workers",
                                  turn_timeout_seconds=5.0)
    created, release = asyncio.Event(), asyncio.Event()
    actual_children, handoff_tasks = [], []
    real_spawn = asyncio.create_subprocess_exec
    initial_tasks = asyncio.all_tasks()

    async def delayed_spawn(*args, **kwargs):
        handoff_tasks.append(asyncio.current_task())
        process = await real_spawn(*args, **kwargs)
        actual_children.append(process)
        created.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)

    async def execute():
        async with provider.episode("double-cancel-consumer"):
            await provider.complete([{"role": "user", "content": "{}"}])

    execution = asyncio.create_task(execute())
    try:
        await asyncio.wait_for(created.wait(), timeout=3.0)
        assert len(actual_children) == 1 and actual_children[0].returncode is None
        assert execution.cancel() is True
        # Let the first cancellation propagate into the startup await before
        # cancelling again. The real process remains held at the same handoff.
        for _ in range(5):
            await asyncio.sleep(0)
        assert not execution.done()
        assert execution.cancel() is True
        for _ in range(5):
            await asyncio.sleep(0)
        assert not execution.done(), "Cleanup must retain ownership until startup hands off the child"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(execution, timeout=3.0)
        record = provider.records["double-cancel-consumer"]
        assert record["process_id"] == actual_children[0].pid
        assert record["exit_code"] == actual_children[0].returncode
        assert record["protocol_status"] == "FAILED"
        assert record["report_completed"] is False
        assert "LOCAL_AGENT_CANCELLED" in record["errors"]
        assert record["request_count"] == provider.calls == 0
        assert record["process_creation_complete"] is True
        assert_reaped(record)
        assert all(task.done() for task in handoff_tasks)
        await asyncio.sleep(0)
        assert asyncio.all_tasks() - initial_tasks == set()
    finally:
        # Retain cleanup ownership independently of the implementation being
        # tested, including the old bug where its record lost the real child.
        release.set()
        for process in actual_children:
            if process.stdin is not None:
                process.stdin.close()
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await asyncio.wait_for(process.wait(), timeout=2.0)
        remaining = asyncio.all_tasks() - initial_tasks
        for task in remaining:
            task.cancel()
        if remaining:
            await asyncio.wait_for(asyncio.gather(*remaining, return_exceptions=True), timeout=3.0)


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["missing_exit", "nonzero_exit", "missing_request",
                                       "duplicate_request", "withheld_report", "missing_creation_complete"])
async def test_contradictory_saved_process_record_cannot_certify_completion(tmp_path, corruption):
    agent = write_agent(tmp_path / "completed.py")
    result = await run_local_agent(tmp_path / "completed", agent, healthy=True)
    assert result["status"] == "PASS" and result["complete"] is True
    original = result["trials"][0]["local_agent_execution"]
    source_hash = result["agent"]["source_hash"]
    assert _valid_process(original, source_hash) is True
    changed = deepcopy(original)
    if corruption == "missing_exit":
        changed.pop("exit_code")
    elif corruption == "nonzero_exit":
        changed["exit_code"] = 71
    elif corruption == "missing_request":
        changed["requests"].pop(0)
    elif corruption == "duplicate_request":
        assert len(changed["requests"]) > 1
        changed["requests"][1]["request_id"] = changed["requests"][0]["request_id"]
    elif corruption == "missing_creation_complete":
        changed.pop("process_creation_complete")
    else:
        changed["requests"][-1]["delivery_status"] = "WITHHELD"
    assert _valid_process(changed, source_hash) is False
    assert _valid_process(original, source_hash) is True
