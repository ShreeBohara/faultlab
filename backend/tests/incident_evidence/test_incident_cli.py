"""CLI admission and real offline replay: saved evidence never selects code."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import struct
import zipfile

import pytest

from app.cli.incident_evidence import main
from app.incident_evidence import bundles, payments, runner
from app.incident_evidence.models import IntegrityError, PAYMENTS, canonical, digest


def _fail_execution(*args, **kwargs):
    raise AssertionError("inspection dispatched a subject")


def _tree(path):
    return {str(file.relative_to(path)): sha256(file.read_bytes()).hexdigest()
            for file in path.rglob("*") if file.is_file()}


@pytest.mark.parametrize("case,status,exit_code,effects", [
    ("healthy", "PASS", 0, 1), ("reconcile", "PASS", 0, 1),
    ("blind_retry", "VIOLATION", 1, 2), ("two_intents", "PASS", 0, 2),
    ("wrong_receipt", "VIOLATION", 1, 1), ("payload_conflict", "PASS", 0, 1),
    ("stopped", "INCOMPLETE", 2, 1), ("untriggered", "INCOMPLETE", 2, 0),
])
def test_cli_runs_one_installed_payment_case_with_honest_exit_status(tmp_path, capsys, case, status, exit_code, effects):
    output = tmp_path / "run"
    assert main(["run", "--task", "payments", "--candidate", case, "--output", str(output)]) == exit_code
    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary == json.loads((output / "summary.json").read_text())
    assert summary["status"] == status
    assert summary["new_subject_execution"] is True
    assert summary["managed_provider_calls"] == summary["managed_provider_spend_dollars"] == 0
    assert "provider_spend_dollars" not in summary  # External activity is not metered here.
    assert summary["source_bundle_digest"] is None
    result = bundles.inspect_bundle(summary["paths"]["zip"]).envelope
    assert result.assessment.status == status
    assert len(result.effects) == effects
    assert result.identity.subject_id == "installed-payment-" + case
    assert len(list(output.rglob("payment.sqlite3"))) == 1
    assert (output / "report.html").is_file()
    assert all(Path(path).is_absolute() for path in summary["paths"].values())
    assert "not production-model or customer validation" in " ".join(summary["limitations"])


@pytest.mark.parametrize("case,recorded_status", [("healthy", "PASS"), ("blind_retry", "VIOLATION"),
                                                ("untriggered", "INCOMPLETE")])
@pytest.mark.parametrize("archive", [False, True])
def test_inspect_exit_zero_means_valid_data_not_a_behavior_pass(tmp_path, capsys, monkeypatch, case, recorded_status, archive):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate=case)
    path = saved["paths"]["zip" if archive else "bundle"]
    before = _tree(tmp_path)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    monkeypatch.setattr(runner, "replay_case", _fail_execution)
    monkeypatch.setattr(runner, "export_orders", _fail_execution)
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    monkeypatch.setattr(payments.sqlite3, "connect", _fail_execution)
    assert main(["inspect", "--bundle", path]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    report = json.loads(captured.out)
    assert report["execution"] == "NOT_RUN"
    assert report["integrity"] == "VALID"
    assert report["recorded_assessment"]["status"] == recorded_status
    assert report["evidence_digest"] == saved["evidence_digest"]
    assert report["managed_provider_calls"] == 0
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("before_case,after_case,before_effects,after_effects", [
    ("blind_retry", "reconcile", 2, 1), ("wrong_receipt", "two_intents", 1, 2),
])
@pytest.mark.parametrize("archive", [False, True])
def test_replay_copied_data_runs_explicit_corrected_candidate_in_new_world(
        tmp_path, capsys, before_case, after_case, before_effects, after_effects, archive):
    original_root = tmp_path / "original"
    original = runner.run_case(original_root, task=PAYMENTS, candidate=before_case)
    source = bundles.inspect_bundle(original["paths"]["bundle"])
    portable = tmp_path / ("copied.zip" if archive else "copied")
    if archive:
        shutil.copyfile(original["paths"]["zip"], portable)
    else:
        shutil.copytree(original["paths"]["bundle"], portable)
    shutil.rmtree(original_root)
    output = tmp_path / "fresh"
    assert main(["replay", "--bundle", str(portable), "--candidate", after_case, "--output", str(output)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    fresh = bundles.inspect_bundle(result["paths"]["bundle"]).envelope
    assert result["new_subject_execution"] is True
    assert result["source_bundle_digest"] == source.manifest["manifest_digest"]
    assert fresh.identity.subject_id == "installed-payment-" + after_case
    assert fresh.identity.subject_source_digest != source.envelope.identity.subject_source_digest
    assert fresh.identity.trial_id != source.envelope.identity.trial_id
    assert fresh.identity.world_id != source.envelope.identity.world_id
    assert fresh.scenario == source.envelope.scenario
    assert len(source.envelope.effects) == before_effects
    assert len(fresh.effects) == after_effects
    assert fresh.assessment.status == "PASS"
    assert source.envelope.assessment.status == "VIOLATION"
    assert bundles.inspect_bundle(portable).envelope == source.envelope


def test_replay_same_unsafe_candidate_fails_freshly_without_selecting_a_fix(tmp_path, capsys):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="blind_retry")
    source = bundles.inspect_bundle(saved["paths"]["bundle"]).envelope
    output = tmp_path / "repeated"
    assert main(["replay", "--bundle", saved["paths"]["bundle"], "--candidate", "blind_retry",
                 "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    fresh = bundles.inspect_bundle(result["paths"]["bundle"]).envelope
    assert fresh.identity.subject_source_digest == source.identity.subject_source_digest
    assert fresh.identity.trial_id != source.identity.trial_id
    assert fresh.identity.world_id != source.identity.world_id
    assert fresh.assessment.status == "VIOLATION"
    assert fresh.assessment.failed_checks == ["PAYMENT_NO_DUPLICATES"]
    assert len(fresh.effects) == 2


@pytest.mark.parametrize("before_case,after_case", [("blind_retry", "healthy"), ("healthy", "reconcile"),
                                                 ("wrong_receipt", "reconcile"), ("reconcile", "two_intents")])
def test_replay_refuses_changed_intentions_or_faults_before_output(tmp_path, capsys, monkeypatch, before_case, after_case):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate=before_case)
    output = tmp_path / "must-not-exist"
    before = _tree(tmp_path / "saved")
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    assert main(["replay", "--bundle", saved["paths"]["bundle"], "--candidate", after_case,
                 "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "INCOMPLETE"
    assert not output.exists()
    assert _tree(tmp_path / "saved") == before


@pytest.mark.parametrize("command", ["run", "replay"])
def test_candidate_selection_is_required_before_any_work(tmp_path, capsys, monkeypatch, command):
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    monkeypatch.setattr(runner, "replay_case", _fail_execution)
    output = tmp_path / "missing-candidate"
    arguments = [command, "--output", str(output)]
    arguments += ["--task", "payments"] if command == "run" else ["--bundle", str(tmp_path / "missing-bundle")]
    with pytest.raises(SystemExit) as failure:
        main(arguments)
    assert failure.value.code == 2
    assert "--candidate" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("command", ["run", "replay"])
def test_candidate_file_is_never_loaded_from_argument_or_bundle(tmp_path, capsys, monkeypatch, command):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="healthy")
    marker = tmp_path / "executed"
    untrusted = tmp_path / "candidate.py"
    untrusted.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    output = tmp_path / "must-not-exist"
    arguments = [command, "--candidate", str(untrusted), "--output", str(output)]
    arguments += ["--task", "payments"] if command == "run" else ["--bundle", saved["paths"]["bundle"]]
    assert main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "INCOMPLETE"
    assert not marker.exists() and not output.exists()


@pytest.mark.parametrize("command", ["inspect", "replay"])
def test_mapping_change_is_integrity_failure_before_replay(tmp_path, capsys, monkeypatch, command):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="blind_retry")
    monkeypatch.setattr(payments, "mapping_digest", lambda: "f" * 64)
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    output = tmp_path / "must-not-exist"
    arguments = [command, "--bundle", saved["paths"]["bundle"]]
    if command == "replay":
        arguments += ["--candidate", "reconcile", "--output", str(output)]
    assert main(arguments) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "INTEGRITY_ERROR"
    assert not output.exists()


def test_extra_candidate_file_is_rejected_without_execution(tmp_path, capsys, monkeypatch):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="healthy")
    path = Path(saved["paths"]["bundle"])
    marker = tmp_path / "executed"
    (path / "candidate.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    assert main(["inspect", "--bundle", str(path)]) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.err)["status"] == "INTEGRITY_ERROR"
    assert captured.out == "" and not marker.exists()


def test_invalid_deflate_is_reported_as_integrity_error(tmp_path, capsys, monkeypatch):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="healthy")
    path = Path(saved["paths"]["zip"])
    data = bytearray(path.read_bytes())
    with zipfile.ZipFile(BytesIO(data)) as archive:
        info = archive.getinfo("evidence.json")
    name_length, extra_length = struct.unpack_from("<HH", data, info.header_offset + 26)
    data[info.header_offset + 30 + name_length + extra_length] = 0x07
    path.write_bytes(data)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    assert main(["inspect", "--bundle", str(path)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "INTEGRITY_ERROR"


def test_existing_output_is_preserved(tmp_path, capsys):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("original")
    before = _tree(output)
    assert main(["run", "--task", "payments", "--candidate", "healthy", "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["status"] == "INCOMPLETE"
    assert captured.out == "" and _tree(output) == before


def test_healthy_flag_does_not_silently_remove_payment_fault(tmp_path, capsys):
    output = tmp_path / "invalid-healthy"
    assert main(["run", "--task", "payments", "--candidate", "reconcile", "--healthy", "--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "INCOMPLETE"
    assert not output.exists()


@pytest.mark.parametrize("error,status,exit_code", [
    (IntegrityError("contradictory saved authority"), "INTEGRITY_ERROR", 3),
    (OSError("unavailable output"), "INCOMPLETE", 2),
    (ValueError("invalid selection"), "INCOMPLETE", 2),
    (KeyboardInterrupt(), "INCOMPLETE", 2),
])
def test_cli_errors_are_distinct_from_behavior_violations(tmp_path, capsys, monkeypatch, error, status, exit_code):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(runner, "run_case", fail)
    output = tmp_path / "must-not-exist"
    assert main(["run", "--task", "payments", "--candidate", "healthy", "--output", str(output)]) == exit_code
    captured = capsys.readouterr()
    assert captured.out == "" and json.loads(captured.err)["status"] == status
    assert not output.exists()


def test_export_summary_records_no_new_subject_execution(tmp_path, monkeypatch):
    """Unit-test export orchestration; orders projection is deliberately substituted."""
    from app.incident_evidence import orders
    value = payments.run_payment_case(tmp_path / "fixture", "healthy")
    source = tmp_path / "selected-store"
    calls = []
    def read(store, episode):
        calls.append((store, episode))
        return {"selected": "source facts"}
    def project(facts):
        assert facts == {"selected": "source facts"}
        return value
    monkeypatch.setattr(orders, "load_orders_facts", read)
    monkeypatch.setattr(orders, "project_orders_facts", project)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    result = runner.export_orders(source, "selected-episode", tmp_path / "export")
    assert calls == [(source, "selected-episode")]
    assert result["new_subject_execution"] is False
    assert result["managed_provider_calls"] == result["managed_provider_spend_dollars"] == 0
    assert any("unmetered" in limitation for limitation in result["limitations"])
    assert bundles.inspect_bundle(result["paths"]["bundle"]).envelope == value



@pytest.mark.parametrize("invalid", ["\ud800", "\udfff"])
@pytest.mark.parametrize("location", ["manifest", "nested_envelope"])
def test_zip_surrogates_are_integrity_errors_without_execution(tmp_path, capsys, monkeypatch, invalid, location):
    saved = runner.run_case(tmp_path / "saved", task=PAYMENTS, candidate="healthy")
    directory = Path(saved["paths"]["bundle"])
    manifest = json.loads((directory / "manifest.json").read_text())
    content = (directory / "evidence.json").read_bytes()
    if location == "manifest":
        manifest["trial_id"] = invalid
    else:
        value = json.loads(content)
        value["source_facts"]["report"]["original"]["note"] = {"nested": [invalid]}
        # Valid UTF-8 transport bytes can contain an invalid escaped surrogate.
        content = json.dumps(value, ensure_ascii=True).encode("utf-8")
        manifest["file"] = {"path": "evidence.json", "sha256": sha256(content).hexdigest(), "size_bytes": len(content)}
        manifest["manifest_digest"] = digest({key: item for key, item in manifest.items() if key != "manifest_digest"})
    archive = tmp_path / "surrogate.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("manifest.json", json.dumps(manifest, ensure_ascii=True).encode("utf-8"))
        zipped.writestr("evidence.json", content)
    before = _tree(tmp_path)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    monkeypatch.setattr(payments.sqlite3, "connect", _fail_execution)
    with pytest.raises(IntegrityError):
        bundles.inspect_bundle(archive)
    assert main(["inspect", "--bundle", str(archive)]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "INTEGRITY_ERROR"
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("escaped", [False, True])
def test_valid_multilingual_and_astral_report_text_survives_zip_inspection(tmp_path, capsys, monkeypatch, escaped):
    from copy import deepcopy
    original = payments.run_payment_case(tmp_path / "fixture", "healthy")
    facts = deepcopy(original.source_facts)
    key, text = "\u5099\u8003\U0001f9ea", "café \u0928\u092e\u0938\u094d\u0924\u0947 \u4ea4\u6613\U0001f9ea e\u0301"
    facts["report"]["original"][key] = text
    facts["report"]["raw_text"] = json.dumps(facts["report"]["original"], ensure_ascii=False) + "\n"
    # Extra report fields are a behavior violation, but faithful Unicode is valid evidence.
    envelope = payments.project_payment_facts(facts)
    assert envelope.assessment.status == "VIOLATION"
    directory = bundles.export_bundle(envelope, tmp_path / "bundle")
    manifest = json.loads((directory / "manifest.json").read_text())
    content = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=escaped).encode("utf-8")
    manifest["file"] = {"path": "evidence.json", "sha256": sha256(content).hexdigest(), "size_bytes": len(content)}
    manifest["manifest_digest"] = digest({name: item for name, item in manifest.items() if name != "manifest_digest"})
    archive = tmp_path / "valid-unicode.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("manifest.json", canonical(manifest).encode("utf-8"))
        zipped.writestr("evidence.json", content)
    monkeypatch.setattr(runner, "run_case", _fail_execution)
    monkeypatch.setattr(payments, "run_payment_case", _fail_execution)
    inspected = bundles.inspect_bundle(archive).envelope
    assert inspected == envelope
    assert inspected.report.original[key] == text
    assert inspected.report.raw_text == facts["report"]["raw_text"]
    assert main(["inspect", "--bundle", str(archive)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    report = json.loads(captured.out)
    assert report["execution"] == "NOT_RUN"
    assert report["recorded_assessment"]["status"] == "VIOLATION"
