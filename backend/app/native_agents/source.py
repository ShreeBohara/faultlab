"""Snapshot an operator-selected native constructor; importing is a child-only action."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.local_agents.source import SourceSnapshot as CheckedSnapshot, read_agent as read_python

PROTOCOL = "faultlab-native-agent/v1"


@dataclass(frozen=True)
class SourceSnapshot(CheckedSnapshot):
    @property
    def descriptor(self):
        return {
            "schema_version": "faultlab-native-agent-source/v1", "protocol": PROTOCOL,
            "source_hash": self.source_hash, "source_filename": self.filename,
            "source_kind": "operator_selected_python_file", "callback": "build_agent",
            "constructor_contract": "build_agent(model, tools) -> ToolCallingAgent",
            "dependency_scope": "single_file_and_reviewed_smolagents_1.26.0_environment",
            "trust": "trusted_local_code", "security_sandbox": False,
        }


@dataclass(frozen=True)
class AgentSource:
    content: bytes
    source_hash: str
    filename: str

    def freeze(self, output_dir):
        directory = Path(output_dir).resolve() / "agent-source"
        directory.mkdir(mode=0o700, exist_ok=False)
        path = directory / "agent.py"
        with path.open("xb") as stream:
            stream.write(self.content)
        path.chmod(0o400)
        snapshot = SourceSnapshot(path, self.source_hash, self.filename)
        snapshot.verify()
        with (directory / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(snapshot.descriptor, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return snapshot


def read_agent(path):
    source = read_python(path)
    return AgentSource(source.content, source.source_hash, source.filename)
