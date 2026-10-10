"""Read and snapshot an operator-selected single Python source file without importing it."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

MAX_SOURCE_BYTES = 262_144
PROTOCOL = "faultlab-local-action/v1"


def _read_regular(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_SOURCE_BYTES:
            raise ValueError("A bounded regular Python source file is required")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read(MAX_SOURCE_BYTES + 1)
        if not content or len(content) > MAX_SOURCE_BYTES:
            raise ValueError("Local agent source is empty or too large")
        content.decode("utf-8", errors="strict")
        return content
    finally:
        os.close(fd)


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    source_hash: str
    filename: str

    @property
    def descriptor(self) -> dict:
        return {"schema_version": "faultlab-local-agent-source/v1", "protocol": PROTOCOL,
                "source_hash": self.source_hash, "source_filename": self.filename,
                "source_kind": "operator_selected_python_file", "callback": "decide",
                "dependency_scope": "single_file_and_python_standard_library",
                "trust": "trusted_local_code", "security_sandbox": False}

    def verify(self) -> None:
        if sha256(_read_regular(self.path)).hexdigest() != self.source_hash:
            raise ValueError("Local agent snapshot changed")


@dataclass(frozen=True)
class AgentSource:
    content: bytes
    source_hash: str
    filename: str

    def freeze(self, output_dir) -> SourceSnapshot:
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


def read_agent(path) -> AgentSource:
    selected = Path(path).expanduser().absolute()
    if selected.suffix != ".py" or selected.is_symlink():
        raise ValueError("Select a regular .py file explicitly")
    content = _read_regular(selected)
    return AgentSource(content, sha256(content).hexdigest(), selected.name)
