"""Adversarial data-only imports, using real persisted synthetic payment facts."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import zipfile

import pytest

from app.incident_evidence import bundles, payments, runner
from app.incident_evidence.models import IntegrityError, canonical, digest


@pytest.fixture
def envelope(tmp_path):
    return payments.run_payment_case(tmp_path / "execution", "healthy")


@pytest.fixture
def bundle(tmp_path, envelope):
    return bundles.export_bundle(envelope, tmp_path / "bundle")


def _bytes(directory):
    return {name: (directory / name).read_bytes() for name in bundles.NAMES}


def _zip(path, entries, *, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return path


def _replace_evidence(directory, value):
    """Repair transport hashes, so a test reaches semantic validation."""
    value["facts_digest"] = digest(value["source_facts"])
    value["digest"] = digest({k: v for k, v in value.items() if k != "digest"})
    raw = (canonical(value) + "\n").encode()
    (directory / "evidence.json").write_bytes(raw)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["evidence_digest"] = value["digest"]
    manifest["file"] = {"path": "evidence.json", "sha256": sha256(raw).hexdigest(), "size_bytes": len(raw)}
    manifest["manifest_digest"] = digest({k: v for k, v in manifest.items() if k != "manifest_digest"})
    (directory / "manifest.json").write_text(canonical(manifest) + "\n")


def _fail_execution(*args, **kwargs):
    raise AssertionError("inspection dispatched execution or opened a historical store")


@pytest.mark.parametrize("archive", [False, True])
def test_portable_inspection_needs_only_two_data_files(bundle, tmp_path, monkeypatch, archive):
    copied = tmp_path / "portable"
    shutil.copytree(bundle, copied)
    before = _bytes(copied)
    expected = bundles.inspect_bundle(copied).envelope
    shutil.rmtree(tmp_path / "execution")
    shutil.rmtree(bundle)
    path = bundles.export_zip(copied, tmp_path / "portable.zip") if archive else copied
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    monkeypatch.setattr(payments.sqlite3, "connect", _fail_execution)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    result = bundles.inspect_bundle(path)
    assert result.envelope == expected
    assert result.envelope.assessment.status == "PASS"
    assert set(copied.iterdir()) == {copied / name for name in bundles.NAMES}
    assert _bytes(copied) == before
    assert not (tmp_path / "execution").exists()


@pytest.mark.parametrize("extra", ["candidate.py", "harness", ".DS_Store"])
def test_directory_inventory_rejects_extra_content(bundle, extra):
    (bundle / extra).write_text("raise AssertionError('must never execute')")
    with pytest.raises(IntegrityError):
        bundles.inspect_bundle(bundle)


@pytest.mark.parametrize("target", ["directory", "parent", "evidence", "manifest"])
def test_symlink_inputs_are_rejected(bundle, tmp_path, target):
    if target == "directory":
        path = tmp_path / "linked"
        path.symlink_to(bundle, target_is_directory=True)
    elif target == "parent":
        parent = tmp_path / "linked-parent"
        parent.symlink_to(tmp_path, target_is_directory=True)
        path = parent / bundle.name
    else:
        name = "evidence.json" if target == "evidence" else "manifest.json"
        saved = tmp_path / ("saved-" + name)
        (bundle / name).rename(saved)
        (bundle / name).symlink_to(saved)
        path = bundle
    with pytest.raises(IntegrityError, match="Symlink"):
        bundles.inspect_bundle(path)


def test_fifo_is_rejected_without_waiting_for_a_writer(bundle):
    path = bundle / "evidence.json"
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(IntegrityError, match="Nonregular"):
        bundles.inspect_bundle(bundle)


@pytest.mark.parametrize("name", ["manifest.json", "evidence.json"])
def test_directory_member_size_is_bounded_before_read(bundle, monkeypatch, name):
    monkeypatch.setattr(bundles, "MAX_MANIFEST" if name == "manifest.json" else "MAX_BYTES",
                        (bundle / name).stat().st_size - 1)
    with pytest.raises(IntegrityError, match="oversized"):
        bundles.inspect_bundle(bundle)


@pytest.mark.parametrize("names", [
    ["manifest.json", "manifest.json"],
    ["manifest.json", "evidence.json", "candidate.py"],
    ["manifest.json", "../evidence.json"],
    ["manifest.json", "/evidence.json"],
    ["manifest.json", "nested/evidence.json"],
    ["manifest.json", "evidence.json/"],
    ["manifest.json", "EVIDENCE.JSON"],
    ["manifest.json", "evidence\\.json"],
])
def test_zip_inventory_rejects_duplicates_and_paths(bundle, tmp_path, names):
    raw = _bytes(bundle)
    path = tmp_path / "bad.zip"
    if names == ["manifest.json", "manifest.json"]:
        with pytest.warns(UserWarning, match="Duplicate name"):
            _zip(path, [(name, raw.get(name, b"untrusted")) for name in names])
    else:
        _zip(path, [(name, raw.get(name, b"untrusted")) for name in names])
    with pytest.raises(IntegrityError, match="inventory"):
        bundles.inspect_bundle(path)
    assert not (tmp_path / "evidence.json").exists()


@pytest.mark.parametrize("file_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFDIR])
def test_zip_nonregular_members_rejected(bundle, tmp_path, file_type):
    raw = _bytes(bundle)
    info = zipfile.ZipInfo("evidence.json")
    info.create_system = 3
    info.external_attr = (file_type | 0o600) << 16
    path = _zip(tmp_path / "nonregular.zip", [("manifest.json", raw["manifest.json"]),
                                             (info, raw["evidence.json"])])
    with pytest.raises(IntegrityError, match="entry type"):
        bundles.inspect_bundle(path)


@pytest.mark.parametrize("compression", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_only_declared_zip_compression_is_admitted(bundle, tmp_path, compression):
    path = _zip(tmp_path / "unsupported.zip", _bytes(bundle).items(), compression=compression)
    with pytest.raises(IntegrityError, match="entry type"):
        bundles.inspect_bundle(path)


def test_compressed_members_obey_expanded_size_limit(bundle, tmp_path, monkeypatch):
    path = _zip(tmp_path / "large-expanded.zip", [
        ("manifest.json", (bundle / "manifest.json").read_bytes()),
        ("evidence.json", b" " * 100_000)])
    assert path.stat().st_size < 4096
    monkeypatch.setattr(bundles, "MAX_BYTES", 4096)
    with pytest.raises(IntegrityError, match="entry type or size"):
        bundles.inspect_bundle(path)


def test_archive_file_size_is_bounded(bundle, tmp_path, monkeypatch):
    path = bundles.export_zip(bundle, tmp_path / "bounded.zip")
    monkeypatch.setattr(bundles, "MAX_ARCHIVE", path.stat().st_size - 1)
    with pytest.raises(IntegrityError, match="oversized"):
        bundles.inspect_bundle(path)


@pytest.mark.parametrize("kind", ["not_zip", "truncated", "crc", "deflate"])
def test_malformed_archives_are_integrity_errors(bundle, tmp_path, kind):
    path = bundles.export_zip(bundle, tmp_path / "malformed.zip")
    data = bytearray(path.read_bytes())
    if kind == "not_zip":
        data = bytearray(b"not an archive")
    elif kind == "truncated":
        data = data[:-30]
    else:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            info = archive.getinfo("evidence.json")
        offset = info.header_offset
        name_len, extra_len = struct.unpack_from("<HH", data, offset + 26)
        start = offset + 30 + name_len + extra_len
        if kind == "deflate":
            data[start] = 0x07  # Reserved DEFLATE block type: invalid compressed stream.
        else:
            central = data.index(b"PK\x01\x02")
            assert data[central + 46:central + 46 + len(info.filename)] == info.filename.encode()
            struct.pack_into("<I", data, central + 16, info.CRC ^ 0xFFFFFFFF)
    path.write_bytes(data)
    with pytest.raises(IntegrityError):
        bundles.inspect_bundle(path)


def test_zip_encrypted_flag_is_refused_before_decryption(bundle, tmp_path):
    path = bundles.export_zip(bundle, tmp_path / "encrypted-flag.zip")
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02")
    flags = struct.unpack_from("<H", data, central + 8)[0]
    struct.pack_into("<H", data, central + 8, flags | 1)
    path.write_bytes(data)
    with pytest.raises(IntegrityError, match="entry type"):
        bundles.inspect_bundle(path)


@pytest.mark.parametrize("kind", ["raw_file", "manifest_hash", "file_hash", "trial_id", "task_type", "extra_field"])
def test_manifest_and_transport_identity_are_verified(bundle, kind):
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text())
    if kind == "raw_file":
        with (bundle / "evidence.json").open("ab") as stream:
            stream.write(b" ")
    else:
        if kind == "manifest_hash":
            manifest["manifest_digest"] = "f" * 64
        elif kind == "file_hash":
            manifest["file"]["sha256"] = "f" * 64
        elif kind == "extra_field":
            manifest["execute"] = "candidate.py"
        else:
            manifest[kind] = "different-identity"
        if kind != "manifest_hash":
            manifest["manifest_digest"] = digest({k: v for k, v in manifest.items() if k != "manifest_digest"})
        path.write_text(canonical(manifest))
    with pytest.raises(IntegrityError):
        bundles.inspect_bundle(bundle)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'{"x":NaN}',
                                   b'{"x":Infinity}', b'{"x":-Infinity}', b'\xff', b'{'])
def test_json_parser_rejects_ambiguous_or_nonfinite_content(raw):
    with pytest.raises(IntegrityError):
        bundles.parse_json(raw)


@pytest.mark.parametrize("change", ["source_ref", "source_ref_binding", "attempt_ref", "normalized_payload", "normalized_report",
                                      "source_payload", "source_identity", "mapping_identity", "unknown_source"])
def test_rehashed_import_still_requires_structural_and_source_consistency(bundle, change):
    value = json.loads((bundle / "evidence.json").read_text())
    if change == "source_ref":
        value["effects"][0]["source_ref"] = "/effects/999"
    elif change == "source_ref_binding":
        value["effects"][0]["source_ref"] = "/intents/0"  # Resolves, but is not this effect's authority.
    elif change == "attempt_ref":
        value["observations"][0]["attempt_id"] = "invented-attempt"
    elif change == "normalized_payload":
        value["effects"][0]["payload"]["amount_minor"] += 1
        value["effects"][0]["payload_digest"] = digest(value["effects"][0]["payload"])
    elif change == "normalized_report":
        value["report"]["original"]["overall"] = "UNRESOLVED"
    elif change == "source_payload":
        value["source_facts"]["effects"][0]["payload"]["amount_minor"] += 1
    elif change in ("source_identity", "mapping_identity"):
        field = "subject_source_digest" if change == "source_identity" else "mapping_digest"
        value["identity"][field] = "f" * 64
        value["source_facts"]["metadata"]["identity"][field] = "f" * 64
    else:
        value["source_facts"]["execute"] = "untrusted.py"
    _replace_evidence(bundle, value)
    with pytest.raises(IntegrityError):
        bundles.inspect_bundle(bundle)


def test_changed_installed_mapping_cannot_reinterpret_old_bundle(bundle, monkeypatch):
    monkeypatch.setattr(payments, "mapping_digest", lambda: "f" * 64)
    with pytest.raises(IntegrityError, match="identity mismatch"):
        bundles.inspect_bundle(bundle)


def test_text_in_preserved_report_is_data_and_html_escaped(envelope, tmp_path, monkeypatch):
    from app.incident_evidence.report import write_report
    facts = deepcopy(envelope.source_facts)
    marker = tmp_path / "executed"
    code = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    facts["report"]["original"]["untrusted_text"] = "<script>" + code + "</script>"
    facts["report"]["raw_text"] = canonical(facts["report"]["original"])
    value = payments.project_payment_facts(facts)
    assert value.assessment.status == "VIOLATION"
    directory = bundles.export_bundle(value, tmp_path / "text-only")
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    inspected = bundles.inspect_bundle(directory)
    assert inspected.envelope.report.original == facts["report"]["original"]
    html_path = tmp_path / "report.html"
    write_report(inspected.envelope, html_path)
    assert "<script>" not in html_path.read_text()
    assert "&lt;script&gt;" in html_path.read_text()
    assert not marker.exists()


def test_export_refuses_existing_output_without_changing_it(bundle, envelope, tmp_path):
    before = _bytes(bundle)
    with pytest.raises(FileExistsError):
        bundles.export_bundle(envelope, bundle)
    assert _bytes(bundle) == before
    archive = bundles.export_zip(bundle, tmp_path / "existing.zip")
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        bundles.export_zip(bundle, archive)
    assert archive.read_bytes() == original


def test_invalid_export_creates_no_output(envelope, tmp_path):
    value = envelope.model_dump(mode="json")
    value["effects"][0]["source_ref"] = "/missing"
    output = tmp_path / "must-not-exist"
    with pytest.raises(IntegrityError):
        bundles.export_bundle(value, output)
    assert not output.exists()
