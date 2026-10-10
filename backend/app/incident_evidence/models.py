"""Bounded incident records, not a universal task scorer or authenticity claim.

Wrong receipts and duplicate business effects are admissible facts. Structural
integrity protects their faithful representation; task mappings judge behavior.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

VERSION = "faultlab-incident-evidence/v1"
ORDERS = "orders.upgrade_then_confirm/v1"
PAYMENTS = "payments.pay_invoice/v1"
MAX_BYTES = 8 * 1024 * 1024
Id = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"^/")]


class IntegrityError(ValueError):
    """Evidence is malformed, inconsistent with its source, or has changed."""


def canonical(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    try:
        serialized.encode("utf-8")
    except UnicodeEncodeError as error:
        raise IntegrityError("Incident JSON contains invalid Unicode") from error
    return serialized


def digest(value) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def hashed_payload(value):
    return {"payload": value, "payload_digest": digest(value)}


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class Identity(Model):
    task_type: Literal["orders.upgrade_then_confirm/v1", "payments.pay_invoice/v1"]
    trial_id: Id
    world_id: Id
    subject_id: Id
    subject_source_digest: Digest
    runtime_digest: Digest
    task_contract_digest: Digest
    configuration_digest: Digest
    mapping_digest: Digest
    source_mode: Literal["offline_fixture"] = "offline_fixture"
    evidence_origin: Literal["persisted_synthetic_execution"] = "persisted_synthetic_execution"


class Position(Model):
    # Named source clocks must not be flattened into an invented global order.
    clock: Literal["lab_event", "world_event", "payment_event", "tool_call"]
    sequence: int = Field(ge=0)
    tick: int | None = Field(default=None, ge=0)


class Operation(Model):
    intent_id: Id
    action: Id
    scope: Id
    payload: dict[str, JsonValue]
    payload_digest: Digest
    source_ref: Ref


class Attempt(Model):
    attempt_id: Id
    call_id: Id
    intent_id: Id | None
    action: Id
    operation_key: str | None = Field(default=None, max_length=512)
    # Unrecorded request bytes remain unknown rather than reconstructed dispatch.
    payload: dict[str, JsonValue] | None
    payload_digest: Digest | None
    source_ref: Ref
    position: Position | None = None


class Effect(Model):
    effect_id: Id
    intent_id: Id | None
    operation_key: str | None = Field(default=None, max_length=512)
    payload: dict[str, JsonValue]
    payload_digest: Digest
    receipt: dict[str, JsonValue] | None = None
    source_ref: Ref
    position: Position | None = None


class Observation(Model):
    observation_id: Id
    attempt_id: Id | None
    intent_id: Id | None
    transport: Literal["ok", "timeout", "error", "unknown"]
    payload: JsonValue
    payload_digest: Digest
    source_ref: Ref
    position: Position | None = None


class Report(Model):
    status: Literal["DELIVERED", "WITHHELD", "ABSENT"]
    original: JsonValue | None
    raw_text: str | None = Field(default=None, max_length=65536)
    interpreted: JsonValue | None = None
    source_ref: Ref


class Exposure(Model):
    fault_id: Id
    triggered: bool | None
    witness: dict[str, JsonValue] | None
    source_ref: Ref


class Check(Model):
    check_id: Id
    passed: bool
    details: str = Field(default="", max_length=2000)
    evidence_refs: list[Ref] = Field(default_factory=list, max_length=256)


class Lifecycle(Model):
    state: Literal["COMPLETED", "INCOMPLETE"]
    authority_complete: bool
    cleanup_complete: bool
    reason: str | None = Field(default=None, max_length=2000)
    missing: list[Id] = Field(default_factory=list, max_length=64)


class Assessment(Model):
    status: Literal["PASS", "VIOLATION", "INCOMPLETE"]
    failed_checks: list[Id] = Field(max_length=64)
    incomplete_reasons: list[Id] = Field(max_length=128)


class Envelope(Model):
    schema_version: Literal["faultlab-incident-evidence/v1"] = VERSION
    schema_digest: Digest
    identity: Identity
    scenario: dict[str, JsonValue]
    operations: list[Operation] = Field(max_length=16)
    attempts: list[Attempt] = Field(max_length=64)
    effects: list[Effect] = Field(max_length=256)
    observations: list[Observation] = Field(max_length=1024)
    report: Report
    required_fault_ids: list[Id] = Field(max_length=16)
    faults: list[Exposure] = Field(max_length=16)
    checks: list[Check] = Field(max_length=64)
    lifecycle: Lifecycle
    assessment: Assessment
    # Each mapping admits a closed set of task-specific source records. This is
    # developer evidence, never automatically an input to an optimizer/model.
    source_facts: dict[str, JsonValue]
    facts_digest: Digest
    digest: Digest


def schema_digest():
    return digest(Envelope.model_json_schema())


def resolve_ref(facts, pointer):
    value = facts
    try:
        if not isinstance(pointer, str) or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
            raise ValueError("Invalid JSON pointer escape")
        for part in pointer.split("/")[1:]:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not part.isdecimal() or str(int(part)) != part:
                    raise ValueError("Invalid source list index")
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value[part]
            else:
                raise ValueError("Reference does not identify a source record")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise IntegrityError("Dangling source reference") from error
    return value


def assessment_for(envelope):
    missing = list(envelope.lifecycle.missing)
    if envelope.lifecycle.state != "COMPLETED":
        missing.append("EXECUTION_INCOMPLETE")
    if not envelope.lifecycle.authority_complete:
        missing.append("AUTHORITY_INCOMPLETE")
    if not envelope.lifecycle.cleanup_complete:
        missing.append("CLEANUP_INCOMPLETE")
    if envelope.report.status != "DELIVERED":
        missing.append("REPORT_NOT_DELIVERED")
    if not envelope.checks:
        missing.append("CHECKS_UNAVAILABLE")
    exposures = {f.fault_id: f for f in envelope.faults}
    if set(exposures) != set(envelope.required_fault_ids):
        missing.append("FAULT_LEDGER_INCOMPLETE")
    if any(fid not in exposures or exposures[fid].triggered is not True
           or not exposures[fid].witness for fid in envelope.required_fault_ids):
        missing.append("REQUIRED_FAULT_NOT_WITNESSED")
    failures = [check.check_id for check in envelope.checks if not check.passed]
    return Assessment(status="INCOMPLETE" if missing else "VIOLATION" if failures else "PASS",
                      failed_checks=failures, incomplete_reasons=sorted(set(missing)))


def validate_structure(value) -> Envelope:
    try:
        envelope = Envelope.model_validate(value)
        serialized = canonical(envelope)
    except (TypeError, ValueError, RecursionError) as error:
        raise IntegrityError("Invalid incident schema or JSON value") from error
    if len(serialized.encode("utf-8")) > MAX_BYTES:
        raise IntegrityError("Incident evidence exceeds its size bound")
    body = envelope.model_dump(mode="json")
    recorded_digest = body.pop("digest")
    if (envelope.schema_digest != schema_digest() or digest(body) != recorded_digest
            or digest(envelope.source_facts) != envelope.facts_digest):
        raise IntegrityError("Incident identity or content digest mismatch")
    for collection, field in ((envelope.operations, "intent_id"), (envelope.attempts, "attempt_id"),
                              (envelope.effects, "effect_id"), (envelope.observations, "observation_id"),
                              (envelope.faults, "fault_id"), (envelope.checks, "check_id")):
        identifiers = [getattr(item, field) for item in collection]
        if len(identifiers) != len(set(identifiers)):
            raise IntegrityError("Duplicate internal record identity")
    if len(envelope.required_fault_ids) != len(set(envelope.required_fault_ids)):
        raise IntegrityError("Duplicate declared fault identity")
    intentions = {item.intent_id for item in envelope.operations}
    attempts = {item.attempt_id for item in envelope.attempts}
    for item in [*envelope.operations, *envelope.attempts, *envelope.effects, *envelope.observations]:
        resolve_ref(envelope.source_facts, item.source_ref)
        if item.payload is None and isinstance(item, Attempt):
            if item.payload_digest is not None:
                raise IntegrityError("Unknown attempt payload has a claimed digest")
        elif digest(item.payload) != item.payload_digest:
            raise IntegrityError("Record payload digest mismatch")
        if item.intent_id is not None and item.intent_id not in intentions:
            raise IntegrityError("Dangling intended-operation reference")
        if isinstance(item, Observation) and item.attempt_id is not None and item.attempt_id not in attempts:
            raise IntegrityError("Dangling attempt reference")
    for item in envelope.faults:
        resolve_ref(envelope.source_facts, item.source_ref)
    for check in envelope.checks:
        for ref in check.evidence_refs:
            resolve_ref(envelope.source_facts, ref)
    resolve_ref(envelope.source_facts, envelope.report.source_ref)
    if envelope.report.status == "ABSENT" and (envelope.report.original is not None or envelope.report.raw_text is not None
                                                or envelope.report.interpreted is not None):
        raise IntegrityError("Absent report contradicts preserved original")
    if envelope.report.status == "DELIVERED" and envelope.report.original is None:
        raise IntegrityError("Delivered report is missing its original content")
    if assessment_for(envelope) != envelope.assessment:
        raise IntegrityError("Assessment contradicts completeness or recorded checks")
    return envelope


def seal(**fields) -> Envelope:
    """Used only by installed task mappings, followed by their source validation."""
    fields.update(schema_version=VERSION, schema_digest=schema_digest(),
                  facts_digest=digest(fields["source_facts"]), digest="0" * 64,
                  assessment={"status": "INCOMPLETE", "failed_checks": [], "incomplete_reasons": []})
    candidate = Envelope.model_validate(fields)
    candidate.assessment = assessment_for(candidate)
    body = candidate.model_dump(mode="json")
    body.pop("digest")
    candidate.digest = digest(body)
    return validate_structure(candidate)
