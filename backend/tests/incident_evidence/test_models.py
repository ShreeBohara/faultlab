"""Adversarial structure tests using synthetic, deliberately non-domain source facts.

These records exercise the common evidence boundary only. They are not valid
orders/payment executions and must not be used as mapper or scorer fixtures.
"""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from app.incident_evidence.models import (
    IntegrityError, MAX_BYTES, ORDERS, canonical, digest, resolve_ref, seal, validate_structure,
)


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _payload(value):
    return {"payload": deepcopy(value), "payload_digest": _digest(value)}


def _fields(*, fault=False):
    request = {"target": "synthetic-item-1", "units": 1}
    receipt = {"service_receipt_id": "service-receipt-1", "result": "committed"}
    facts = {
        "intent": request, "request": request,
        "effect": {"committed": True, "target": "synthetic-item-1"},
        "observation": receipt, "report": {"result": "done"},
        "fault": {"triggered": True, "at": "after-commit"},
        "check": {"synthetic_check": True},
        "escaped": {"a/b": {"~key": [{"value": 1}]}, "a~2b": 2},
    }
    return {
        "identity": {
            "task_type": ORDERS, "trial_id": "trial-1", "world_id": "world-1",
            "subject_id": "subject-1", "subject_source_digest": "1" * 64,
            "runtime_digest": "2" * 64, "task_contract_digest": "3" * 64,
            "configuration_digest": "4" * 64, "mapping_digest": "5" * 64,
        },
        "scenario": {"fixture": "common-structure-test-only"},
        "operations": [{"intent_id": "intent-1", "action": "synthetic-write",
                        "scope": "synthetic-service", **_payload(request), "source_ref": "/intent"}],
        "attempts": [{"attempt_id": "attempt-1", "call_id": "framework-call-1",
                      "intent_id": "intent-1", "action": "synthetic-write", "operation_key": "key-1",
                      **_payload(request), "source_ref": "/request",
                      "position": {"clock": "tool_call", "sequence": 0}}],
        "effects": [{"effect_id": "effect-1", "intent_id": "intent-1", "operation_key": "key-1",
                     **_payload(facts["effect"]), "receipt": receipt, "source_ref": "/effect",
                     "position": {"clock": "world_event", "sequence": 1}}],
        "observations": [{"observation_id": "observation-1", "attempt_id": "attempt-1",
                          "intent_id": "intent-1", "transport": "ok", **_payload(receipt),
                          "source_ref": "/observation"}],
        "report": {"status": "DELIVERED", "original": facts["report"], "source_ref": "/report"},
        "required_fault_ids": ["fault-1"] if fault else [],
        "faults": [{"fault_id": "fault-1", "triggered": True,
                    "witness": facts["fault"], "source_ref": "/fault"}] if fault else [],
        "checks": [{"check_id": "synthetic-property", "passed": True, "evidence_refs": ["/check"]}],
        "lifecycle": {"state": "COMPLETED", "authority_complete": True, "cleanup_complete": True},
        "source_facts": facts,
    }


def _raw(*, fault=False):
    return seal(**_fields(fault=fault)).model_dump(mode="json")


def _rehash(value):
    """Simulate a changed envelope whose attacker recomputes its outer digest."""
    value["digest"] = _digest({key: item for key, item in value.items() if key != "digest"})
    return value


def test_healthy_empty_fault_ledger_is_structurally_complete():
    record = validate_structure(_raw())
    assert record.required_fault_ids == record.faults == []
    assert record.assessment.status == "PASS"
    assert record.assessment.incomplete_reasons == []


def test_duplicate_business_effects_are_admitted_and_judged_by_recorded_checks():
    fields = _fields()
    second = deepcopy(fields["effects"][0])
    second["effect_id"] = "effect-2"
    fields["effects"].append(second)
    fields["checks"][0]["passed"] = False
    record = seal(**fields)
    assert [effect.effect_id for effect in record.effects] == ["effect-1", "effect-2"]
    assert {effect.intent_id for effect in record.effects} == {"intent-1"}
    assert {effect.operation_key for effect in record.effects} == {"key-1"}
    assert record.assessment.status == "VIOLATION"


def test_wrong_receipt_for_another_intent_is_admitted_without_reassigning_effect():
    fields = _fields()
    second = deepcopy(fields["operations"][0])
    second.update(intent_id="intent-2", **_payload({"target": "synthetic-item-2", "units": 1}))
    fields["operations"].append(second)
    fields["attempts"][0]["intent_id"] = "intent-2"
    fields["observations"][0]["intent_id"] = "intent-2"
    fields["checks"][0]["passed"] = False
    record = seal(**fields)
    assert record.effects[0].intent_id == "intent-1"
    assert record.observations[0].intent_id == "intent-2"
    assert record.observations[0].payload == record.effects[0].receipt
    assert record.assessment.status == "VIOLATION"


def test_retries_keep_distinct_attempts_and_can_reuse_external_labels_and_receipts():
    fields = _fields()
    retry = deepcopy(fields["attempts"][0])
    retry["attempt_id"] = "attempt-2"
    fields["attempts"].append(retry)
    observed = deepcopy(fields["observations"][0])
    observed.update(observation_id="observation-2", attempt_id="attempt-2")
    fields["observations"].append(observed)
    record = seal(**fields)
    assert len(record.attempts) == len(record.observations) == 2
    assert len(record.effects) == 1
    assert record.attempts[0].call_id == record.attempts[1].call_id
    assert record.observations[0].payload == record.observations[1].payload


@pytest.mark.parametrize("collection", ["operations", "attempts", "effects", "observations", "faults", "checks"])
def test_duplicate_internal_record_ids_are_integrity_errors(collection):
    value = _raw(fault=True)
    value[collection].append(deepcopy(value[collection][0]))
    with pytest.raises(IntegrityError, match="Duplicate internal record identity"):
        validate_structure(_rehash(value))


def test_duplicate_declared_fault_ids_are_not_extra_exposure():
    value = _raw(fault=True)
    value["required_fault_ids"].append("fault-1")
    with pytest.raises(IntegrityError, match="Duplicate declared fault identity"):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("collection", ["attempts", "effects", "observations"])
def test_dangling_intended_operation_reference_is_rejected(collection):
    value = _raw()
    value[collection][0]["intent_id"] = "unrecorded-intent"
    with pytest.raises(IntegrityError, match="Dangling intended-operation reference"):
        validate_structure(_rehash(value))


def test_dangling_attempt_reference_is_rejected():
    value = _raw()
    value["observations"][0]["attempt_id"] = "other-trial-attempt"
    with pytest.raises(IntegrityError, match="Dangling attempt reference"):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("collection", ["operations", "attempts", "effects", "observations", "faults", "report", "checks"])
def test_all_declared_source_references_must_resolve(collection):
    value = _raw(fault=True)
    if collection == "report":
        value["report"]["source_ref"] = "/missing"
    elif collection == "checks":
        value["checks"][0]["evidence_refs"] = ["/missing"]
    else:
        value[collection][0]["source_ref"] = "/missing"
    with pytest.raises(IntegrityError, match="Dangling source reference"):
        validate_structure(_rehash(value))


def test_source_pointer_escaping_and_array_index_are_unambiguous():
    assert resolve_ref(_fields()["source_facts"], "/escaped/a~1b/~0key/0") == {"value": 1}


@pytest.mark.parametrize("suffix", ["-1", "01", "1.0", "2"])
def test_invalid_or_missing_array_reference_is_rejected(suffix):
    with pytest.raises(IntegrityError):
        resolve_ref(_fields()["source_facts"], "/escaped/a~1b/~0key/" + suffix)


def test_malformed_pointer_escape_is_not_treated_as_a_literal_source_key():
    value = _raw()
    value["report"]["source_ref"] = "/escaped/a~2b"
    with pytest.raises(IntegrityError):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("field", ["digest", "facts_digest", "schema_digest"])
def test_envelope_facts_and_schema_digests_are_checked_independently(field):
    value = _raw()
    value[field] = "0" * 64
    if field != "digest":
        _rehash(value)
    with pytest.raises(IntegrityError, match="digest mismatch"):
        validate_structure(value)


def test_changed_source_facts_are_rejected_even_with_a_new_outer_digest():
    value = _raw()
    value["source_facts"]["effect"]["committed"] = False
    with pytest.raises(IntegrityError, match="digest mismatch"):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("collection", ["operations", "attempts", "effects", "observations"])
def test_each_record_payload_digest_is_checked(collection):
    value = _raw()
    value[collection][0]["payload_digest"] = "0" * 64
    with pytest.raises(IntegrityError, match="Record payload digest mismatch"):
        validate_structure(_rehash(value))


def test_unknown_attempt_payload_is_preserved_as_unknown_not_an_empty_request():
    fields = _fields()
    fields["attempts"][0].update(payload=None, payload_digest=None)
    record = seal(**fields)
    assert record.attempts[0].payload is record.attempts[0].payload_digest is None
    raw = record.model_dump(mode="json")
    raw["attempts"][0]["payload_digest"] = _digest({})
    with pytest.raises(IntegrityError, match="Unknown attempt payload"):
        validate_structure(_rehash(raw))


def test_incomplete_lifecycle_retains_failed_checks_effects_and_withheld_report():
    fields = _fields()
    fields["checks"][0]["passed"] = False
    fields["lifecycle"].update(state="INCOMPLETE", authority_complete=False,
                               cleanup_complete=False, missing=["MISSING_FINAL_STATE"])
    fields["report"].update(status="WITHHELD", raw_text='{"result":"done"}',
                            interpreted={"claimed_success": True})
    record = seal(**fields)
    assert record.assessment.status == "INCOMPLETE"
    assert record.assessment.failed_checks == ["synthetic-property"]
    assert len(record.effects) == 1
    assert record.report.original == {"result": "done"}
    assert record.report.raw_text == '{"result":"done"}'
    assert set(record.assessment.incomplete_reasons) == {
        "EXECUTION_INCOMPLETE", "AUTHORITY_INCOMPLETE", "CLEANUP_INCOMPLETE",
        "MISSING_FINAL_STATE", "REPORT_NOT_DELIVERED",
    }


@pytest.mark.parametrize("triggered,witness", [(False, {"seen": True}), (None, {"seen": True}), (True, None), (True, {})])
def test_declared_fault_requires_both_trigger_and_nonempty_witness(triggered, witness):
    fields = _fields(fault=True)
    fields["faults"][0].update(triggered=triggered, witness=witness)
    record = seal(**fields)
    assert record.assessment.status == "INCOMPLETE"
    assert "REQUIRED_FAULT_NOT_WITNESSED" in record.assessment.incomplete_reasons


def test_empty_fault_ledger_does_not_vacuously_pass_a_declared_fault():
    fields = _fields(fault=True)
    fields["faults"] = []
    record = seal(**fields)
    assert record.assessment.status == "INCOMPLETE"
    assert set(record.assessment.incomplete_reasons) == {
        "FAULT_LEDGER_INCOMPLETE", "REQUIRED_FAULT_NOT_WITNESSED",
    }


def test_missing_checks_do_not_vacuously_pass():
    fields = _fields()
    fields["checks"] = []
    record = seal(**fields)
    assert record.assessment.status == "INCOMPLETE"
    assert "CHECKS_UNAVAILABLE" in record.assessment.incomplete_reasons


@pytest.mark.parametrize("assessment", [
    {"status": "VIOLATION", "failed_checks": [], "incomplete_reasons": []},
    {"status": "PASS", "failed_checks": ["invented"], "incomplete_reasons": []},
    {"status": "INCOMPLETE", "failed_checks": [], "incomplete_reasons": ["invented"]},
])
def test_recomputed_outer_hash_cannot_legitimize_a_contradictory_assessment(assessment):
    value = _raw()
    value["assessment"] = assessment
    with pytest.raises(IntegrityError, match="Assessment contradicts"):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("preserved", ["original", "raw_text", "interpreted"])
def test_absent_report_cannot_carry_report_content(preserved):
    value = _raw()
    value["report"].update(status="ABSENT", original=None, raw_text=None, interpreted=None)
    value["report"][preserved] = "fabricated report"
    value["assessment"] = {"status": "INCOMPLETE", "failed_checks": [],
                           "incomplete_reasons": ["REPORT_NOT_DELIVERED"]}
    with pytest.raises(IntegrityError):
        validate_structure(_rehash(value))


def test_delivered_report_requires_original_content():
    value = _raw()
    value["report"]["original"] = None
    with pytest.raises(IntegrityError, match="missing its original"):
        validate_structure(_rehash(value))


@pytest.mark.parametrize("collection,limit", [
    ("operations", 16), ("attempts", 64), ("effects", 256),
    ("observations", 1024), ("faults", 16), ("checks", 64), ("required_fault_ids", 16),
])
def test_collection_size_limits_are_enforced_before_assessment(collection, limit):
    value = _raw(fault=True)
    value[collection] = [deepcopy(value[collection][0]) for _ in range(limit + 1)]
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(value)


def test_intention_limit_allows_its_exact_boundary():
    fields = _fields()
    base = fields["operations"][0]
    fields["operations"] = [dict(deepcopy(base), intent_id=f"intent-{i}") for i in range(1, 17)]
    assert len(seal(**fields).operations) == 16


@pytest.mark.parametrize("location", ["envelope", "identity", "attempt", "position"])
def test_unknown_fields_are_rejected_at_nested_boundaries(location):
    value = _raw()
    target = {"envelope": value, "identity": value["identity"],
              "attempt": value["attempts"][0], "position": value["attempts"][0]["position"]}[location]
    target["extra_field"] = "ignored evidence is unsafe"
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(value)


@pytest.mark.parametrize("value", [True, "1", 1.0, -1])
def test_position_sequence_is_a_strict_nonnegative_integer(value):
    raw = _raw()
    raw["attempts"][0]["position"]["sequence"] = value
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(raw)


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_inside_json_facts_are_rejected(nonfinite):
    value = _raw()
    value["source_facts"]["nested"] = {"values": [nonfinite]}
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(value)


def test_serialized_size_bound_does_not_silently_truncate_source_facts():
    value = _raw()
    value["source_facts"]["oversized"] = "x" * MAX_BYTES
    with pytest.raises(IntegrityError, match="size bound"):
        validate_structure(value)


@pytest.mark.parametrize("location", ["subject_id", "source_ref", "raw_text", "check_details"])
def test_text_bounds(location):
    value = _raw()
    if location == "subject_id":
        value["identity"]["subject_id"] = "x" * 129
    elif location == "source_ref":
        value["report"]["source_ref"] = "/" + "x" * 512
    elif location == "raw_text":
        value["report"]["raw_text"] = "x" * 65537
    else:
        value["checks"][0]["details"] = "x" * 2001
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(value)


def test_unimplemented_task_profiles_are_not_admitted_as_generic_plugins():
    value = _raw()
    value["identity"]["task_type"] = "external.plugin/arbitrary"
    with pytest.raises(IntegrityError, match="Invalid incident schema"):
        validate_structure(value)



@pytest.mark.parametrize("invalid", ["\ud800", "\udfff"])
@pytest.mark.parametrize("as_key", [False, True])
def test_canonical_rejects_unpaired_surrogates_as_integrity_errors(invalid, as_key):
    value = {invalid: "value"} if as_key else {"nested": [{"text": invalid}]}
    with pytest.raises(IntegrityError, match="invalid Unicode"):
        canonical(value)
    with pytest.raises(IntegrityError, match="invalid Unicode"):
        digest(value)


@pytest.mark.parametrize("invalid", ["\ud800", "\udfff"])
@pytest.mark.parametrize("location", ["nested_value", "nested_key", "report_text"])
def test_envelope_nested_surrogates_are_integrity_errors(invalid, location):
    value = _raw()
    if location == "nested_value":
        value["source_facts"]["text"] = {"nested": [{"text": invalid}]}
    elif location == "nested_key":
        value["source_facts"]["text"] = {invalid: "value"}
    else:
        value["report"]["raw_text"] = invalid
    # Invalid Unicode cannot have a canonical digest: reject it before hashing.
    with pytest.raises(IntegrityError):
        validate_structure(value)


@pytest.mark.parametrize("text", ["café", "\u0928\u092e\u0938\u094d\u0924\u0947", "\u4ea4\u6613\U0001f9ea", "e\u0301"])
def test_valid_unicode_retains_canonical_bytes_and_structural_acceptance(text):
    fields = _fields()
    fields["source_facts"]["unicode"] = {"\u5099\u8003\U0001f9ea": text}
    record = seal(**fields)
    assert validate_structure(record.model_dump(mode="json")) == record
    assert record.source_facts["unicode"]["\u5099\u8003\U0001f9ea"] == text
    value = {"text": text}
    assert canonical(value) == json.dumps(value, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False)
    assert digest(value) == _digest(value)
