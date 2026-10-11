"""The trial envelope: what one execution of a plan produced, sealed so it can be checked.

Shapes follow the v2 architecture (section 4.4): a ``TrialPlan`` fixed before admission, one
``TrialAttempt`` executing it, an append-only list of ``EvidenceEvent`` on three planes
(agent-visible, evaluator, orchestrator), ``Finding`` records from fixed-code properties, and a
``ResultVector`` that separates how the execution ended from what the task outcome was.

Integrity follows ``app.incident_evidence.models``: every payload carries its digest, every event
and the report point back into ``source_facts`` by JSON pointer, and the whole envelope carries a
digest over its body. ``seal`` writes those digests; ``validate_structure`` refuses anything that
does not add up. Nothing here is a scorer: findings are recorded, never computed.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from faultlab.core.budgets import Caps
from faultlab.core.canonical import canonical_json, content_hash
from faultlab.core.errors import IntegrityError
from faultlab.core.ids import Digest, Id, Ref
from faultlab.core.model import StrictModel

SCHEMA_VERSION = "faultlab-trial-envelope/v2"
MAX_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 4096

Plane = Literal["agent_visible", "evaluator", "orchestrator"]
Certainty = Literal["observed", "inferred", "unknown"]
ExecutionState = Literal["COMPLETED", "INFRA_ERROR", "STOPPED", "PENDING_EVIDENCE"]
TaskState = Literal["COMPLETED", "SAFE_UNRESOLVED", "CORRECTLY_REFUSED", "VIOLATION"]
PropertyResult = Literal["PASS", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"]
Severity = Literal["critical", "major", "minor"]
NotTriggeredReason = Literal["target_not_reached", "target_not_committed", "pre_effect_failure",
                             "avoided_by_alternative_path", "unclassified"]
Kind = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(max_length=2000)]
IsoTime = Annotated[str, StringConstraints(min_length=1, max_length=64)]


def canonical(value) -> str:
    serialized = canonical_json(value)
    try:
        serialized.encode("utf-8")
    except UnicodeEncodeError as error:
        raise IntegrityError("Evidence JSON contains invalid Unicode") from error
    return serialized


def digest(value) -> str:
    return content_hash(value)


def hashed_payload(value) -> dict:
    return {"payload": value, "payload_digest": digest(value)}


class EvidenceEvent(StrictModel):
    seq: int = Field(ge=0)
    plane: Plane
    kind: Kind
    source: Name                         # kernel | broker | adapter | lab | staging:<provider> | legacy:<type>
    certainty: Certainty
    operation_id: Id | None = None
    attempt_ref: Id | None = None
    causal_parents: list[int] = Field(default_factory=list, max_length=64)
    logical_time: int | None = Field(default=None, ge=0)
    wall_time: IsoTime | None = None
    # Named source clocks are kept beside ``seq``; ``seq`` orders the list, it does not claim that
    # events on different clocks happened in that order.
    clock: Name | None = None
    clock_sequence: int | None = Field(default=None, ge=0)
    payload: JsonValue
    payload_digest: Digest
    source_ref: Ref | None = None


class Finding(StrictModel):
    property_id: Id
    property_version: Name
    result: PropertyResult
    family: Kind
    severity: Severity
    witnesses: list[int] = Field(default_factory=list, max_length=256)
    note: Note = ""


class FaultPlacement(StrictModel):
    fault_id: Id
    family: Name
    tool: Name | None = None
    service: Name | None = None
    occurrence: int | None = Field(default=None, ge=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class FaultSchedule(StrictModel):
    placements: list[FaultPlacement] = Field(default_factory=list, max_length=64)
    seed: int | None = None


class FaultExposure(StrictModel):
    fault_id: Id
    configured: bool = True
    triggered: bool | None
    trigger_time: int | None = Field(default=None, ge=0)
    attempt_ref: Id | None = None
    not_triggered_reason: NotTriggeredReason | None = None
    note: Annotated[str, StringConstraints(max_length=600)] | None = None


class ExposureSummary(StrictModel):
    faults: list[FaultExposure] = Field(default_factory=list, max_length=64)
    required_fault_ids: list[Id] = Field(default_factory=list, max_length=64)

    @property
    def all_required_triggered(self) -> bool | None:
        """True when every required fault triggered, False when one did not, None when unknown."""
        by_id = {fault.fault_id: fault for fault in self.faults}
        states = [by_id[fid].triggered if fid in by_id else None for fid in self.required_fault_ids]
        if any(state is None for state in states):
            return None
        return all(states)


class ClaimScore(StrictModel):
    """Beliefs versus effects (architecture section 5). ``UNSCORED`` until the oracle exists."""
    status: Literal["UNSCORED", "SCORED"] = "UNSCORED"
    claims: dict[str, JsonValue] = Field(default_factory=dict)
    mismatches: list[Name] = Field(default_factory=list, max_length=64)


class CostSummary(StrictModel):
    model_calls: int = Field(default=0, ge=0)
    http_attempts: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    dollars_measured: float | None = Field(default=None, ge=0)
    dollars_reserved: float | None = Field(default=None, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0)
    ticks: int = Field(default=0, ge=0)


class ExecutionIdentity(StrictModel):
    """What makes two results comparable (architecture section 11). Unknown parts stay None."""
    pack_id: Name
    pack_digest: Digest | None = None
    kernel_digest: Digest | None = None
    adapter_id: Name
    adapter_digest: Digest | None = None
    model: Name
    model_settings_digest: Digest | None = None
    prompt_digest: Digest | None = None
    properties_digest: Digest | None = None
    protocol_version: Name
    configuration_digest: Digest | None = None


class ResultVector(StrictModel):
    execution: ExecutionState
    task: TaskState | None
    findings: list[Finding] = Field(default_factory=list, max_length=256)
    claims: ClaimScore = Field(default_factory=ClaimScore)
    exposure: ExposureSummary = Field(default_factory=ExposureSummary)
    evidence_completeness: Literal["complete", "incomplete", "unavailable"]
    cost: CostSummary = Field(default_factory=CostSummary)
    identity: ExecutionIdentity

    @model_validator(mode="after")
    def completed_executions_have_a_task_state(self):
        if self.execution == "COMPLETED" and self.task is None:
            raise ValueError("a completed execution needs a task outcome")
        return self


class AgentManifest(StrictModel):
    adapter_id: Name
    version: Name | None = None
    model: Name
    settings_digest: Digest | None = None
    prompt_digest: Digest | None = None


class EnvSpec(StrictModel):
    kind: Literal["simulator", "staging"]
    digest: Digest | None = None
    capabilities: dict[str, JsonValue] = Field(default_factory=dict)


class RepetitionPolicy(StrictModel):
    k: int = Field(default=1, ge=1)
    pairing: Name | None = None
    seed: int | None = None


class TrialPlan(StrictModel):
    pack_id: Name
    pack_digest: Digest | None = None
    scenario_id: Name
    fixture_id: Name | None = None
    fixture_digest: Digest | None = None
    agent: AgentManifest
    environment: EnvSpec
    schedule: FaultSchedule = Field(default_factory=FaultSchedule)
    properties_digest: Digest | None = None
    protocol_version: Name
    caps: Caps = Field(default_factory=Caps)
    repetition: RepetitionPolicy = Field(default_factory=RepetitionPolicy)


def plan_hash(plan: TrialPlan) -> str:
    return digest(plan)


class TrialAttempt(StrictModel):
    attempt_id: Id
    plan_hash: Digest
    parent_attempt: Id | None = None
    lifecycle: Literal["CREATED", "READY", "RUNNING", "SETTLING", "TERMINAL"]
    terminal_reason: Annotated[str, StringConstraints(max_length=600)] | None = None
    started_at: IsoTime | None = None
    ended_at: IsoTime | None = None


class Report(StrictModel):
    status: Literal["DELIVERED", "WITHHELD", "ABSENT"]
    original: JsonValue | None = None
    raw_text: Annotated[str, StringConstraints(max_length=65536)] | None = None
    interpreted: JsonValue | None = None
    source_ref: Ref | None = None


class SourceDescriptor(StrictModel):
    kind: Literal["legacy_lab_store", "faultlab_v2"]
    projection: Name
    mapping_digest: Digest
    store_identity: Name | None = None
    notes: list[Note] = Field(default_factory=list, max_length=64)


class TrialEnvelope(StrictModel):
    schema_version: Literal["faultlab-trial-envelope/v2"] = SCHEMA_VERSION
    schema_digest: Digest
    plan: TrialPlan
    attempt: TrialAttempt
    events: list[EvidenceEvent] = Field(default_factory=list, max_length=MAX_EVENTS)
    report: Report
    outcome: ResultVector
    source: SourceDescriptor
    # The closed set of source records the envelope was projected from: developer evidence,
    # never automatically an input to a model.
    source_facts: dict[str, JsonValue]
    facts_digest: Digest
    digest: Digest


def schema_digest() -> str:
    return digest(TrialEnvelope.model_json_schema())


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


def validate_structure(value) -> TrialEnvelope:
    """Parse and check an envelope; any contradiction fails closed with ``IntegrityError``."""
    try:
        envelope = TrialEnvelope.model_validate(value)
        serialized = canonical(envelope)
    except (TypeError, ValueError, RecursionError) as error:
        raise IntegrityError(f"Invalid trial envelope: {error}") from error
    if len(serialized.encode("utf-8")) > MAX_BYTES:
        raise IntegrityError("Trial envelope exceeds its size bound")
    body = envelope.model_dump(mode="json")
    recorded_digest = body.pop("digest")
    if envelope.schema_digest != schema_digest():
        raise IntegrityError("Trial envelope schema digest mismatch")
    if digest(body) != recorded_digest or digest(envelope.source_facts) != envelope.facts_digest:
        raise IntegrityError("Trial envelope content digest mismatch")
    if envelope.attempt.plan_hash != plan_hash(envelope.plan):
        raise IntegrityError("Attempt does not name its plan")
    seqs = [event.seq for event in envelope.events]
    if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
        raise IntegrityError("Event sequence is not strictly increasing")
    known = set(seqs)
    for event in envelope.events:
        if digest(event.payload) != event.payload_digest:
            raise IntegrityError("Event payload digest mismatch")
        if any(parent >= event.seq or parent not in known for parent in event.causal_parents):
            raise IntegrityError("Event names a causal parent that is not an earlier event")
        if event.source_ref is not None:
            resolve_ref(envelope.source_facts, event.source_ref)
    for finding in envelope.outcome.findings:
        if any(witness not in known for witness in finding.witnesses):
            raise IntegrityError("Finding cites an event that does not exist")
    fault_ids = [fault.fault_id for fault in envelope.outcome.exposure.faults]
    if len(fault_ids) != len(set(fault_ids)):
        raise IntegrityError("Duplicate fault identity in exposure")
    required = envelope.outcome.exposure.required_fault_ids
    if len(required) != len(set(required)) or not set(required) <= set(fault_ids):
        raise IntegrityError("Required faults must be configured faults")
    if envelope.report.source_ref is not None:
        resolve_ref(envelope.source_facts, envelope.report.source_ref)
    if envelope.report.status == "ABSENT" and (envelope.report.original is not None or envelope.report.raw_text is not None
                                                or envelope.report.interpreted is not None):
        raise IntegrityError("Absent report contradicts preserved content")
    if envelope.report.status == "DELIVERED" and envelope.report.original is None and envelope.report.raw_text is None:
        raise IntegrityError("Delivered report is missing its original content")
    return envelope


def seal(**fields) -> TrialEnvelope:
    """Fill the digests of an envelope under construction, then validate it."""
    fields.update(schema_version=SCHEMA_VERSION, schema_digest=schema_digest(),
                  facts_digest=digest(fields["source_facts"]), digest="0" * 64)
    try:
        candidate = TrialEnvelope.model_validate(fields)
    except (TypeError, ValueError) as error:
        raise IntegrityError(f"Invalid trial envelope: {error}") from error
    body = candidate.model_dump(mode="json")
    body.pop("digest")
    candidate.digest = digest(body)
    return validate_structure(candidate)
