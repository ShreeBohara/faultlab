"""Persisted payment behavior and evidence integrity, without models or network."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from app.incident_evidence.models import IntegrityError, canonical, digest, validate_structure
from app.incident_evidence.payments import (
    CASE_IDS, project_payment_facts, read_payment_facts, run_payment_case, scenario_for_case,
)


@pytest.mark.parametrize("case,status,effect_count,attempt_count", [
    ("healthy", "PASS", 1, 1), ("reconcile", "PASS", 1, 2),
    ("blind_retry", "VIOLATION", 2, 2), ("two_intents", "PASS", 2, 2),
    ("wrong_receipt", "VIOLATION", 1, 2), ("payload_conflict", "PASS", 1, 2),
    ("stopped", "INCOMPLETE", 1, 1), ("untriggered", "INCOMPLETE", 0, 0),
])
def test_real_persisted_cases(tmp_path, case, status, effect_count, attempt_count):
    output = tmp_path / case
    result = run_payment_case(output, case)
    assert result.assessment.status == status
    assert len(result.effects) == effect_count
    assert len(result.attempts) == attempt_count
    with sqlite3.connect(f"file:{output / 'payment.sqlite3'}?mode=ro", uri=True) as db:
        actual = [json.loads(row[0]) for row in db.execute("SELECT data FROM effects ORDER BY rowid")]
        assert len(actual) == effect_count
        assert [row["payload"] for row in actual] == [effect.payload for effect in result.effects]
        assert [row["effect_id"] for row in actual] == [effect.effect_id for effect in result.effects]
    saved = json.loads((output / "incident.json").read_text())
    assert validate_structure(saved) == result
    assert project_payment_facts(read_payment_facts(output / "payment.sqlite3")) == result
    assert "LangGraph" not in result.identity.subject_id
    assert result.scenario["fixture_kind"] == "SYNTHETIC_DETERMINISTIC_PAYMENT"
    if result.report.status == "DELIVERED":
        assert result.report.raw_text.endswith("\n")
        assert json.loads(result.report.raw_text) == result.report.original == result.report.interpreted


def test_reply_loss_is_after_commit_and_lookup_returns_same_receipt(tmp_path):
    result = run_payment_case(tmp_path / "reconcile", "reconcile")
    effect = result.effects[0]
    first, second = result.observations
    assert first.transport == "timeout" and first.payload == {"status": "UNKNOWN", "code": "REPLY_LOST"}
    witness = result.faults[0].witness
    assert effect.position.sequence < witness["trigger_sequence"] < first.position.sequence
    assert first.position.sequence < result.attempts[1].position.sequence < second.position.sequence
    assert second.payload == effect.receipt
    assert result.attempts[1].action == "lookup"
    assert result.report.original["payments"][0]["receipt_id"] == effect.receipt["receipt_id"]


def test_retry_under_new_key_really_commits_duplicate_not_prevented_by_intent_constraint(tmp_path):
    result = run_payment_case(tmp_path / "blind", "blind_retry")
    assert len({effect.intent_id for effect in result.effects}) == 1
    assert len({effect.operation_key for effect in result.effects}) == 2
    assert len({effect.effect_id for effect in result.effects}) == 2
    assert result.effects[0].payload == result.effects[1].payload
    assert result.assessment.failed_checks == ["PAYMENT_NO_DUPLICATES"]
    assert result.report.original["overall"] == "COMPLETED"


def test_wrong_receipt_retains_actual_foreign_receipt_and_false_original_claim(tmp_path):
    result = run_payment_case(tmp_path / "wrong", "wrong_receipt")
    assert result.observations[1].intent_id == "intent-2"
    assert result.observations[1].payload == result.effects[0].receipt
    assert result.effects[0].intent_id == "intent-1"
    claims = result.report.original["payments"]
    assert claims[0]["receipt_id"] == claims[1]["receipt_id"]
    assert claims[1]["intent_id"] == "intent-2" and claims[1]["status"] == "PAID"
    assert result.assessment.failed_checks == ["PAYMENT_REQUIRED_EFFECTS", "PAYMENT_REPORT_TRUTH"]


def test_conflicting_payload_cannot_overwrite_effect_or_return_paid_receipt(tmp_path):
    result = run_payment_case(tmp_path / "conflict", "payload_conflict")
    assert result.attempts[0].operation_key == result.attempts[1].operation_key
    assert result.attempts[0].payload["amount_minor"] == 10000
    assert result.attempts[1].payload["amount_minor"] == 20000
    assert result.effects[0].payload["amount_minor"] == 10000
    assert result.observations[1].transport == "error"
    assert result.observations[1].payload == {"status": "CONFLICT", "code": "KEY_PAYLOAD_CONFLICT"}
    assert "receipt_id" not in result.observations[1].payload


def test_stop_retains_effect_without_inventing_report_or_automatic_retry(tmp_path):
    result = run_payment_case(tmp_path / "stopped", "stopped")
    assert len(result.attempts) == len(result.effects) == 1
    assert result.report.status == "ABSENT" and result.report.original is None and result.report.raw_text is None
    assert result.faults[0].triggered is True
    assert result.lifecycle.state == "INCOMPLETE" and result.lifecycle.cleanup_complete
    assert "REPORT_NOT_DELIVERED" in result.assessment.incomplete_reasons
    assert "EXECUTION_INCOMPLETE" in result.assessment.incomplete_reasons


def test_untriggered_fault_is_not_containment(tmp_path):
    result = run_payment_case(tmp_path / "untriggered", "untriggered")
    assert result.required_fault_ids == ["post-commit-reply-loss"]
    assert result.faults[0].triggered is False and result.faults[0].witness is None
    assert result.effects == [] and result.attempts == []
    assert "REQUIRED_FAULT_NOT_WITNESSED" in result.assessment.incomplete_reasons


def test_candidates_change_subject_not_declared_scenario_and_every_world_is_fresh(tmp_path):
    baseline = run_payment_case(tmp_path / "before", "blind_retry")
    corrected = run_payment_case(tmp_path / "after", "reconcile")
    assert baseline.scenario == corrected.scenario
    assert baseline.identity.subject_source_digest != corrected.identity.subject_source_digest
    assert baseline.identity.world_id != corrected.identity.world_id
    assert baseline.identity.trial_id != corrected.identity.trial_id
    assert scenario_for_case("two_intents") == scenario_for_case("wrong_receipt")
    copied = scenario_for_case("healthy")
    copied["intents"][0]["amount_minor"] = 2
    assert scenario_for_case("healthy")["intents"][0]["amount_minor"] == 10000


@pytest.mark.parametrize("field", ["intents", "attempts", "effects", "observations", "events", "reports", "faults"])
def test_missing_authority_table_remains_incomplete_not_assumed_empty(tmp_path, field):
    output = tmp_path / field
    run_payment_case(output, "reconcile")
    with sqlite3.connect(output / "payment.sqlite3") as db:
        db.execute(f"DROP TABLE {field}")
    facts = read_payment_facts(output / "payment.sqlite3")
    assert facts["report" if field == "reports" else field] is None
    result = project_payment_facts(facts)
    assert result.assessment.status == "INCOMPLETE"
    assert result.lifecycle.authority_complete is False
    assert "PAYMENT_AUTHORITY_" + field.upper() in result.assessment.incomplete_reasons
    if field != "effects":
        assert len(result.effects) == 1


@pytest.mark.parametrize("mutation", ["extra", "bool_amount", "effect_amount", "receipt", "fault", "event", "original", "identity"])
def test_contradictory_or_open_source_facts_refused_even_with_recomputed_payload_hash(tmp_path, mutation):
    facts = deepcopy(run_payment_case(tmp_path / mutation, "reconcile").source_facts)
    if mutation == "extra":
        facts["unexpected"] = True
    elif mutation == "bool_amount":
        facts["intents"][0]["amount_minor"] = True
    elif mutation == "effect_amount":
        facts["effects"][0]["payload"]["amount_minor"] = 2
        facts["effects"][0]["payload_digest"] = digest(facts["effects"][0]["payload"])
    elif mutation == "receipt":
        facts["observations"][1]["payload"]["invoice_id"] = "OTHER"
    elif mutation == "fault":
        facts["faults"][0]["trigger_sequence"] = 1
    elif mutation == "event":
        found = next(event for event in facts["events"] if event["kind"] == "lookup_found")
        found["payload"]["effect_id"] = "other-effect"
    elif mutation == "original":
        facts["report"]["original"]["overall"] = "UNRESOLVED"
    else:
        facts["metadata"]["identity"]["subject_source_digest"] = "0" * 64
    with pytest.raises(IntegrityError):
        project_payment_facts(facts)


def test_sql_primary_key_and_json_disagreement_is_not_ignored(tmp_path):
    output = tmp_path / "sql"
    run_payment_case(output, "healthy")
    with sqlite3.connect(output / "payment.sqlite3") as db:
        db.execute("UPDATE effects SET operation_key='substituted-key'")
    with pytest.raises(IntegrityError, match="provider key"):
        read_payment_facts(output / "payment.sqlite3")


def test_output_refusal_and_explicit_candidate_admission_before_creation(tmp_path):
    output = tmp_path / "kept"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        run_payment_case(output, "healthy")
    alias = tmp_path / "alias"
    alias.symlink_to(output, target_is_directory=True)
    with pytest.raises(FileExistsError):
        run_payment_case(alias, "healthy")
    assert marker.read_text() == "keep"
    absent = tmp_path / "not-created"
    with pytest.raises(ValueError):
        run_payment_case(absent, "arbitrary.module")
    assert not absent.exists()
    assert len(CASE_IDS) == 8


def test_read_refuses_final_database_symlink(tmp_path):
    output = tmp_path / "real"
    run_payment_case(output, "healthy")
    link = tmp_path / "alias.sqlite3"
    link.symlink_to(output / "payment.sqlite3")
    with pytest.raises(IntegrityError, match="symlink"):
        read_payment_facts(link)
    assert project_payment_facts(read_payment_facts(output / "payment.sqlite3")).assessment.status == "PASS"


def test_authority_read_is_one_snapshot_across_concurrent_database_change(tmp_path, monkeypatch):
    output = tmp_path / "snapshot"
    original = run_payment_case(output, "healthy")
    path = output / "payment.sqlite3"
    real_connect = sqlite3.connect
    with real_connect(path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        # Establish WAL/SHM through a real writer transaction before a read-only
        # connection joins it; switching mode alone need not create these files.
        writer.execute("UPDATE trial SET lifecycle=lifecycle")
    changes = []

    class InterleavedReader(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            cursor = super().execute(sql, *args, **kwargs)
            if sql == "SELECT id,metadata,lifecycle FROM trial" and not changes:
                with real_connect(path) as writer:
                    writer.execute("DELETE FROM effects")
                changes.append(True)
            return cursor

    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, factory=InterleavedReader)

    monkeypatch.setattr(sqlite3, "connect", connect)
    facts = read_payment_facts(path)
    assert changes == [True]
    assert project_payment_facts(facts) == original
    with real_connect(path) as writer:
        assert writer.execute("SELECT count(*) FROM effects").fetchone()[0] == 0


def test_malformed_original_report_is_preserved_and_cannot_pass(tmp_path):
    facts = deepcopy(run_payment_case(tmp_path / "malformed", "healthy").source_facts)
    original = {"payments": 17, "overall": "COMPLETED"}
    facts["report"]["original"] = original
    facts["report"]["raw_text"] = json.dumps(original)
    result = project_payment_facts(facts)
    assert result.report.original == original
    assert result.assessment.status == "VIOLATION"
    assert "PAYMENT_REPORT_TRUTH" in result.assessment.failed_checks
