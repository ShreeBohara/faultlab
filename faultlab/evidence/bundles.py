"""Incident bundles v2: a data-only archive of sealed trial envelopes with a digest manifest.

A bundle is a zip file holding ``manifest.json`` and one ``envelopes/<attempt_id>.json`` per
trial. The manifest names the bundle, lists every envelope with its digest, plan hash and
execution identity, and carries its own digest. Reading a bundle re-validates every envelope
(``validate_structure``) and every digest, so a changed byte anywhere is refused. No code
travels in a bundle: replaying one is the reader's own reviewed runner, never something the
bundle brought along.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

from pydantic import Field

from faultlab.core.canonical import canonical_json, content_hash
from faultlab.core.errors import IntegrityError
from faultlab.core.ids import Digest, Id
from faultlab.core.model import StrictModel
from faultlab.evidence.models import TrialEnvelope, validate_structure

BUNDLE_VERSION = "faultlab-envelope-bundle/v2"
MAX_ENVELOPES = 4096
# A hostile archive must fail before it is read: bounded member count, member size and total size.
MAX_MEMBER_BYTES = 16 * 1024 * 1024          # one envelope's own bound (faultlab.evidence.models.MAX_BYTES)
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024


class BundleEntry(StrictModel):
    attempt_id: Id
    path: str = Field(min_length=1, max_length=200)
    digest: Digest                       # the envelope's own sealed digest
    file_sha256: Digest                  # sha256 of the stored bytes
    plan_hash: Digest
    pack_id: str = Field(min_length=1, max_length=200)
    identity_digest: Digest              # content_hash of the envelope's ExecutionIdentity
    execution: str
    task: str | None


class BundleManifest(StrictModel):
    bundle_version: str = BUNDLE_VERSION
    bundle_id: Id
    name: str = Field(min_length=1, max_length=200)
    created_at: str
    notes: list[str] = Field(default_factory=list, max_length=64)
    entries: list[BundleEntry] = Field(default_factory=list, max_length=MAX_ENVELOPES)
    manifest_digest: Digest


def _entry_path(attempt_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in attempt_id)
    return f"envelopes/{safe}.json"


def write_bundle(envelopes: list[TrialEnvelope], path, *, name: str, notes: list[str] | None = None) -> BundleManifest:
    """Write a bundle; every envelope is validated before it is stored."""
    path = Path(path)
    if not envelopes:
        raise IntegrityError("A bundle holds at least one envelope")
    seen: set[str] = set()
    entries, blobs = [], {}
    for envelope in envelopes:
        validate_structure(envelope)
        attempt_id = envelope.attempt.attempt_id
        if attempt_id in seen:
            raise IntegrityError(f"Duplicate attempt {attempt_id} in bundle")
        seen.add(attempt_id)
        data = (canonical_json(envelope) + "\n").encode("utf-8")
        entry_path = _entry_path(attempt_id)
        blobs[entry_path] = data
        entries.append(BundleEntry(attempt_id=attempt_id, path=entry_path, digest=envelope.digest,
                                   file_sha256=__import__("hashlib").sha256(data).hexdigest(), plan_hash=envelope.attempt.plan_hash,
                                   pack_id=envelope.plan.pack_id, identity_digest=content_hash(envelope.outcome.identity),
                                   execution=envelope.outcome.execution, task=envelope.outcome.task))
    body = {"bundle_version": BUNDLE_VERSION, "bundle_id": f"bundle-{content_hash([e.digest for e in entries])[:32]}",
            "name": name, "created_at": datetime.now(timezone.utc).isoformat(), "notes": list(notes or []),
            "entries": [entry.model_dump(mode="json") for entry in entries]}
    manifest = BundleManifest(**body, manifest_digest=content_hash(body))
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
        for entry_path, data in blobs.items():
            archive.writestr(entry_path, data)
    return manifest


def read_bundle(path) -> tuple[BundleManifest, list[TrialEnvelope]]:
    """Read and fully re-validate a bundle; any changed byte, digest or envelope is refused."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENVELOPES + 1:
                raise IntegrityError("Bundle has too many members")
            total = 0
            for info in infos:
                limit = MAX_MANIFEST_BYTES if info.filename == "manifest.json" else MAX_MEMBER_BYTES
                if info.file_size > limit or info.compress_size > limit:
                    raise IntegrityError(f"Bundle member {info.filename} exceeds its size bound")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise IntegrityError("Bundle exceeds its total size bound")
            names = set(archive.namelist())
            if "manifest.json" not in names:
                raise IntegrityError("Bundle has no manifest")
            raw = json.loads(archive.read("manifest.json").decode("utf-8"))
            manifest = BundleManifest.model_validate(raw)
            body = {key: value for key, value in manifest.model_dump(mode="json").items() if key != "manifest_digest"}
            if manifest.bundle_version != BUNDLE_VERSION or content_hash(body) != manifest.manifest_digest:
                raise IntegrityError("Bundle manifest digest mismatch")
            expected = {entry.path for entry in manifest.entries} | {"manifest.json"}
            if names != expected:
                raise IntegrityError("Bundle contents differ from its manifest")
            envelopes = []
            for entry in manifest.entries:
                if archive.getinfo(entry.path).file_size > MAX_MEMBER_BYTES:
                    raise IntegrityError(f"Envelope {entry.attempt_id} exceeds its size bound")
                data = archive.read(entry.path)
                if __import__("hashlib").sha256(data).hexdigest() != entry.file_sha256:
                    raise IntegrityError(f"Stored bytes changed for {entry.attempt_id}")
                envelope = validate_structure(json.loads(data.decode("utf-8")))
                if (envelope.digest != entry.digest or envelope.attempt.attempt_id != entry.attempt_id
                        or envelope.attempt.plan_hash != entry.plan_hash
                        or content_hash(envelope.outcome.identity) != entry.identity_digest):
                    raise IntegrityError(f"Envelope {entry.attempt_id} contradicts the manifest")
                envelopes.append(envelope)
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as error:
        raise IntegrityError(f"Unreadable bundle: {error}") from error
    return manifest, envelopes


def comparable_identities(envelopes: list[TrialEnvelope]) -> dict[str, int]:
    """How many envelopes share each execution identity: only equal identities are comparable."""
    counts: dict[str, int] = {}
    for envelope in envelopes:
        key = content_hash(envelope.outcome.identity)
        counts[key] = counts.get(key, 0) + 1
    return counts
