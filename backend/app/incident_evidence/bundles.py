"""Small data-only incident bundles. Inspection never dispatches a workflow."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import zipfile
import zlib

from .models import Envelope, IntegrityError, MAX_BYTES, canonical, digest
from .validation import validate_evidence

VERSION = "faultlab-incident-bundle/v1"
NAMES = frozenset({"manifest.json", "evidence.json"})
MAX_ARCHIVE = 2 * MAX_BYTES
MAX_MANIFEST = 16_384


def parse_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise IntegrityError("Duplicate JSON field")
            value[key] = item
        return value
    def constant(_):
        raise IntegrityError("Nonfinite JSON value")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise IntegrityError("Invalid incident JSON") from error


def _path(value):
    path = Path(value).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise IntegrityError("Symlink input rejected")
    return path


def read_regular(path, limit):
    path = _path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise IntegrityError("Nonregular or oversized evidence file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                value = stream.read(limit + 1)
            after = os.fstat(fd)
            if len(value) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise IntegrityError("Evidence file changed or exceeded its size bound")
            return value
        finally:
            os.close(fd)
    except OSError as error:
        raise IntegrityError("Cannot read incident file safely") from error


@dataclass(frozen=True)
class InspectedIncident:
    envelope: Envelope
    manifest: dict


def _inspect(payloads):
    if set(payloads) != NAMES:
        raise IntegrityError("Exact data-only incident inventory required")
    manifest = parse_json(payloads["manifest.json"])
    keys = {"schema_version", "artifact_kind", "task_type", "trial_id", "evidence_digest", "file", "manifest_digest"}
    if not isinstance(manifest, dict) or set(manifest) != keys:
        raise IntegrityError("Unknown or missing incident manifest fields")
    if manifest["schema_version"] != VERSION or manifest["artifact_kind"] != "synthetic_incident_evidence":
        raise IntegrityError("Unsupported incident bundle version or kind")
    expected = digest({k: v for k, v in manifest.items() if k != "manifest_digest"})
    content = payloads["evidence.json"]
    if manifest["manifest_digest"] != expected or manifest["file"] != {
        "path": "evidence.json", "sha256": sha256(content).hexdigest(), "size_bytes": len(content)
    }:
        raise IntegrityError("Incident manifest or file digest mismatch")
    envelope = validate_evidence(parse_json(content))
    if (manifest["task_type"] != envelope.identity.task_type or manifest["trial_id"] != envelope.identity.trial_id
            or manifest["evidence_digest"] != envelope.digest):
        raise IntegrityError("Incident task or execution identity mismatch")
    return InspectedIncident(envelope, manifest)


def inspect_bundle(path) -> InspectedIncident:
    """Validate directory or ZIP data with installed mappings and no source execution."""
    path = _path(path)
    if path.is_dir():
        if {p.name for p in path.iterdir()} != NAMES:
            raise IntegrityError("Exact incident directory inventory required")
        return _inspect({name: read_regular(path / name, MAX_MANIFEST if name == "manifest.json" else MAX_BYTES)
                         for name in NAMES})
    archive = read_regular(path, MAX_ARCHIVE)
    try:
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if len(entries) != 2 or {e.filename for e in entries} != NAMES:
                raise IntegrityError("Exact flat ZIP inventory required")
            payloads = {}
            for entry in entries:
                limit = MAX_MANIFEST if entry.filename == "manifest.json" else MAX_BYTES
                file_type = stat.S_IFMT(entry.external_attr >> 16)
                if (entry.is_dir() or file_type not in (0, stat.S_IFREG) or entry.flag_bits & 1
                        or entry.file_size > limit or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise IntegrityError("Unsupported ZIP entry type or size")
                with zipped.open(entry) as member:
                    content = member.read(limit + 1)
                if len(content) != entry.file_size or len(content) > limit:
                    raise IntegrityError("ZIP member size mismatch")
                payloads[entry.filename] = content
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, OSError, EOFError) as error:
        raise IntegrityError("Malformed incident ZIP") from error
    return _inspect(payloads)


def new_output(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("Symlink output rejected")
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def export_bundle(value, output):
    envelope = validate_evidence(value)
    content = (canonical(envelope) + "\n").encode("utf-8")
    manifest = {"schema_version": VERSION, "artifact_kind": "synthetic_incident_evidence",
                "task_type": envelope.identity.task_type, "trial_id": envelope.identity.trial_id,
                "evidence_digest": envelope.digest,
                "file": {"path": "evidence.json", "sha256": sha256(content).hexdigest(), "size_bytes": len(content)}}
    manifest["manifest_digest"] = digest(manifest)
    output = new_output(output)
    (output / "evidence.json").write_bytes(content)
    (output / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    return output


def export_zip(bundle, destination):
    inspected = inspect_bundle(bundle)
    directory = _path(bundle)
    # Capture and verify the same bytes that will be archived, not a second unchecked read.
    payloads = {name: read_regular(directory / name, MAX_MANIFEST if name == "manifest.json" else MAX_BYTES)
                for name in NAMES}
    if _inspect(payloads).envelope.digest != inspected.envelope.digest:
        raise IntegrityError("Bundle changed before archive creation")
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise IntegrityError("Symlink archive destination rejected")
    with destination.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(NAMES):
                archive.writestr(name, payloads[name])
    return destination
