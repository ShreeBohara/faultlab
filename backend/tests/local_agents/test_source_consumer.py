"""Admission does not import code, and execution uses the frozen selected bytes."""
from hashlib import sha256
import json

import pytest

from app.local_agents.source import read_agent
from app.local_agents.transport import LocalAgentProvider


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_source_admission_never_imports_the_selected_module(tmp_path):
    marker = tmp_path / "import-side-effect.txt"
    selected = tmp_path / "author_agent.py"
    selected.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\ndef decide(request):\n    return None\n")
    admitted = read_agent(selected)
    output = tmp_path / "frozen"
    output.mkdir()
    snapshot = admitted.freeze(output)
    assert not marker.exists()
    assert snapshot.path.read_bytes() == selected.read_bytes()
    assert snapshot.source_hash == sha256(selected.read_bytes()).hexdigest()
    assert snapshot.descriptor["security_sandbox"] is False


@pytest.mark.anyio
async def test_editing_original_after_admission_does_not_change_child_execution(tmp_path):
    expected = {"kind": "report", "report": {
        "upgrade_outcome": "NOT_STARTED", "notification_outcome": "NOT_STARTED",
        "overall": "SAFE_UNRESOLVED", "evidence_ids": [], "next_action": {"kind": "ESCALATE"},
    }}
    selected = tmp_path / "outside_agent.py"
    selected.write_text("def decide(request):\n    return " + repr(expected) + "\n")
    original_bytes = selected.read_bytes()
    output = tmp_path / "run"
    output.mkdir()
    snapshot = read_agent(selected).freeze(output)
    selected.write_text("raise RuntimeError('The changed original must not execute')\n")
    provider = LocalAgentProvider(snapshot, output / "workers")
    async with provider.episode("frozen-source-consumer"):
        generation = await provider.complete([{"role": "user", "content": "{}"}])
    assert json.loads(generation.content) == expected
    record = provider.records["frozen-source-consumer"]
    assert record["source_hash"] == sha256(original_bytes).hexdigest()
    assert record["protocol_status"] == "COMPLETED"
    assert record["cleanup_complete"] is True
    assert record["errors"] == []
