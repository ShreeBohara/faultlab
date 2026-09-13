"""FaultLab v1 shared wire contracts. No runtime I/O or provider initialization.

Only trusted code allocates identity. Model proposals use the narrow discriminated
unions below; private records never form model inputs merely by being serializable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Annotated, Literal, Union
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

VERSION = 'faultlab/v1'
SCOPE = 'orders.upgrade_then_confirm/v1'
MODEL_INPUT_TOKEN_LIMIT = 32000
MODEL_OUTPUT_TOKEN_LIMIT = 2000
CAMPAIGN_TOKEN_LIMIT = 6000 * (MODEL_INPUT_TOKEN_LIMIT + MODEL_OUTPUT_TOKEN_LIMIT)
Id = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
Digest = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
Text = Annotated[str, StringConstraints(max_length=600)]
Service = Literal['orders', 'notifications']
Tool = Literal['get_order', 'update_order', 'get_operation_status', 'send_confirmation']
Status = Literal['PENDING', 'SUCCEEDED', 'FAILED', 'UNKNOWN']
StoredStatus = Literal['PENDING', 'SUCCEEDED', 'FAILED']
Invariant = Literal['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8']
Split = Literal['development', 'promotion', 'final_audit']
Arm = Literal['B0', 'B1', 'L']
Origin = Literal['prototype', 'faultlab_evaluation']
Purpose = Literal['discovery', 'reproduction', 'reduction', 'intervention', 'source_validation', 'challenge', 'promotion', 'final_audit', 'portability', 'selection_comparison', 'diagnostic_profile']
Outcome = Literal['COMPLETED', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED', 'VIOLATION', 'LAB_ERROR']
CampaignState = Literal['IDLE', 'SELECTING', 'RUNNING', 'SCORING', 'NO_CHANGE', 'DIAGNOSING', 'REPRODUCING', 'REDUCING', 'INTERVENING', 'CANDIDATE_VALIDATION', 'CHALLENGING', 'EVALUATING', 'PROMOTED', 'REJECTED', 'WAITING_EVIDENCE', 'STOPPED', 'COMPLETED', 'ERROR']
DiagnosticKind = Literal['POLICY_GAP', 'CONTRACT_EVIDENCE_GAP', 'INCONCLUSIVE']
Condition = Literal['always', 'upgrade_receipt_missing', 'notification_receipt_missing', 'current_operation_pending', 'notification_operation_pending', 'upgrade_outcome_uncertain', 'notification_outcome_uncertain', 'upgrade_terminal_failure', 'notification_terminal_failure', 'upgrade_succeeded', 'notification_succeeded', 'receipt_missing']
Hook = Literal['after_upgrade_response', 'before_confirmation', 'after_notification_response', 'before_final_report']


def new_id(prefix: str = 'id') -> str:
    return f'{prefix}-{uuid4().hex}'


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode='json')
    def encode_nested(item):
        if isinstance(item, BaseModel):
            return item.model_dump(mode='json')
        raise TypeError('Canonical JSON requires JSON values or validated models')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False, default=encode_nested)


def content_hash(value) -> str:
    return sha256(canonical_json(value).encode('utf-8')).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True, str_strip_whitespace=False, strict=True)

    @field_validator('*')
    @classmethod
    def utc_timestamps(cls, value):
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset().total_seconds() != 0):
            raise ValueError('timestamps must be timezone-aware UTC')
        return value


class Record(StrictModel):
    schema_version: Literal['faultlab/v1'] = VERSION


class EmptyArguments(StrictModel):
    pass


class UpgradeArguments(StrictModel):
    desired_shipping: Literal['express']


class StatusArguments(StrictModel):
    service: Service


class GetOrderAction(StrictModel):
    kind: Literal['tool'] = 'tool'
    tool: Literal['get_order']
    arguments: EmptyArguments


class UpdateOrderAction(StrictModel):
    kind: Literal['tool'] = 'tool'
    tool: Literal['update_order']
    arguments: UpgradeArguments


class GetStatusAction(StrictModel):
    kind: Literal['tool'] = 'tool'
    tool: Literal['get_operation_status']
    arguments: StatusArguments


class SendConfirmationAction(StrictModel):
    kind: Literal['tool'] = 'tool'
    tool: Literal['send_confirmation']
    arguments: EmptyArguments


class NoNextAction(StrictModel):
    kind: Literal['NONE', 'ESCALATE']


class CheckNextAction(StrictModel):
    kind: Literal['CHECK_EXISTING_UPGRADE', 'CHECK_EXISTING_NOTIFICATION']
    operation_id: Id


NextAction = Annotated[Union[NoNextAction, CheckNextAction], Field(discriminator='kind')]


class TaskReport(StrictModel):
    upgrade_outcome: Literal['NOT_STARTED', 'PENDING', 'SUCCEEDED', 'FAILED', 'UNKNOWN']
    notification_outcome: Literal['NOT_STARTED', 'PENDING', 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'NOT_REQUIRED']
    overall: Literal['COMPLETED', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED']
    evidence_ids: list[Id] = Field(max_length=18)
    next_action: NextAction


class ReportAction(StrictModel):
    kind: Literal['report']
    report: TaskReport


ToolAction = Annotated[Union[GetOrderAction, UpdateOrderAction, GetStatusAction, SendConfirmationAction], Field(discriminator='tool')]
ActorAction = Annotated[Union[ToolAction, ReportAction], Field(discriminator='kind')]


class TaskIntent(Record):
    task_id: Id
    order_id: Id
    desired_shipping: Literal['express'] = 'express'
    expected_version: int = Field(ge=1, le=1000000)
    template_version: Literal['confirmation/v1'] = 'confirmation/v1'
    upgrade_operation_id: Id
    notification_operation_id: Id
    upgrade_idempotency_key: Id
    notification_idempotency_key: Id
    upgrade_intent_hash: Digest
    notification_intent_hash: Digest
    task_text: str = Field(min_length=1, max_length=2000)


class Receipt(StrictModel):
    receipt_id: Id
    operation_id: Id
    service: Service
    order_id: Id
    intent_hash: Digest
    status: Literal['SUCCEEDED', 'FAILED']
    terminal_tick: int = Field(ge=0, le=25)
    committed_version: int | None = Field(default=None, ge=1)
    effect_id: Id | None = None
    failure_code: Literal['UPGRADE_REJECTED', 'VERSION_CONFLICT'] | None = None


class Order(StrictModel):
    order_id: Id
    applied_shipping: Literal['standard', 'express']
    requested_shipping: Literal['standard', 'express']
    version: int = Field(ge=1)
    last_upgrade_operation_id: Id | None = None


class OperationData(StrictModel):
    operation_id: Id
    service: Service
    order_id: Id
    intent_hash: Digest
    status: Status
    receipt: Receipt | None = None


class ToolResult(StrictModel):
    call_id: Id
    tool: Tool
    transport: Literal['ok', 'timeout', 'error']
    operation_id: Id | None = None
    order_id: Id | None = None
    status: Status | None = None
    observed_version: int | None = Field(default=None, ge=1)
    receipt_id: Id | None = None
    retry_after_ticks: int | None = Field(default=None, ge=1, le=20)
    error_code: str | None = Field(default=None, max_length=80)
    data: Order | OperationData | None = None


class PublicObservation(Record):
    evidence_id: Id
    episode_id: Id
    call_id: Id
    delivered_tick: int = Field(ge=0, le=20)
    result: ToolResult
    observed_operation_id: Id | None = None
    observed_order_id: Id | None = None
    observed_intent_hash: Digest | None = None
    source_receipt_id: Id | None = None


class F1Parameters(StrictModel):
    response_delay_ms: int = Field(ge=1500, le=3000)


class F2Parameters(StrictModel):
    completion_delay_ticks: int = Field(ge=1, le=20)
    terminal_status: Literal['SUCCEEDED', 'FAILED']
    failure_code: Literal['UPGRADE_REJECTED'] | None

    @model_validator(mode='after')
    def consistent_failure(self):
        if (self.terminal_status == 'FAILED') != (self.failure_code == 'UPGRADE_REJECTED'):
            raise ValueError('terminal status/failure code mismatch')
        return self


class F3Parameters(StrictModel):
    versions_back: int = Field(ge=1, le=3)


class F4Parameters(StrictModel):
    failure_count: int = Field(ge=1, le=18)


class PrimitiveBase(StrictModel):
    target_tool: Tool
    target_service: Service
    occurrence: int = Field(ge=1, le=18)

    @model_validator(mode='after')
    def valid_target(self):
        service = 'notifications' if self.target_tool == 'send_confirmation' else 'orders'
        if self.target_tool != 'get_operation_status' and self.target_service != service:
            raise ValueError('tool/service mismatch')
        return self


class F1(PrimitiveBase):
    kind: Literal['F1']
    target_tool: Literal['update_order', 'send_confirmation']
    parameters: F1Parameters


class F2(PrimitiveBase):
    kind: Literal['F2']
    target_tool: Literal['update_order']
    target_service: Literal['orders']
    parameters: F2Parameters


class F3(PrimitiveBase):
    kind: Literal['F3']
    target_tool: Literal['get_order']
    target_service: Literal['orders']
    parameters: F3Parameters


class F4(PrimitiveBase):
    kind: Literal['F4']
    parameters: F4Parameters


FaultPrimitive = Annotated[Union[F1, F2, F3, F4], Field(discriminator='kind')]


class FaultSpec(StrictModel):
    schema_version: Literal['faultlab/v1'] = VERSION
    scope: Literal['orders.upgrade_then_confirm/v1'] = SCOPE
    seed: int = Field(ge=0, le=2147483647)
    primitives: list[FaultPrimitive] = Field(max_length=2)


class ExplorerOutput(StrictModel):
    fault_spec: FaultSpec
    hypothesis: Text

    @model_validator(mode='after')
    def not_healthy(self):
        if not self.fault_spec.primitives:
            raise ValueError('Explorer must select one or two primitives')
        return self


class NoArgStep(StrictModel):
    op: Literal['read_current_operation', 'read_notification_operation', 'read_order', 'defer_unresolved']
    only_if: Condition = 'always'


class WaitStep(StrictModel):
    op: Literal['wait_ticks']
    ticks: int = Field(ge=1, le=4)
    only_if: Condition = 'always'


class ServiceStep(StrictModel):
    op: Literal['retry_original_request', 'report_terminal_failure']
    service: Service
    only_if: Condition = 'always'


class ReceiptStep(StrictModel):
    op: Literal['require_receipt']
    service: Service
    status: Literal['SUCCEEDED']
    only_if: Condition = 'always'


PolicyStep = Annotated[Union[NoArgStep, WaitStep, ServiceStep, ReceiptStep], Field(discriminator='op')]


class PolicyRule(StrictModel):
    hook: Hook
    when: Condition
    steps: list[PolicyStep] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def notification_retry_hook(self):
        if any(s.op == 'retry_original_request' and s.service == 'notifications' for s in self.steps):
            if self.hook != 'after_notification_response':
                raise ValueError('notification retries require after_notification_response')
        return self


class RecoveryPolicy(StrictModel):
    scope: Literal['orders.upgrade_then_confirm/v1'] = SCOPE
    parent_version: Id
    rules: list[PolicyRule] = Field(max_length=8)


class CandidatePolicy(RecoveryPolicy):
    rules: list[PolicyRule] = Field(min_length=1, max_length=8)


class MechanicCandidate(StrictModel):
    candidate: CandidatePolicy
    explanation: Text


class MechanicNoChange(StrictModel):
    no_change_reason: Annotated[str, StringConstraints(min_length=1, max_length=600)]


MechanicOutput = Union[MechanicCandidate, MechanicNoChange]


class DiagnosticProposal(StrictModel):
    proposed_kind: DiagnosticKind
    hypothesis: Text
    evidence_ids: list[Id] = Field(min_length=1, max_length=36)
    requested_intervention_id: Id | None


class EpisodeBudget(StrictModel):
    http_attempts: int = Field(default=18, ge=1, le=18)
    actor_calls: int = Field(default=8, ge=1, le=8)
    wait_cycles: int = Field(default=4, ge=0, le=4)
    ticks: int = Field(default=20, ge=1, le=20)
    policy_steps: int = Field(default=32, ge=0, le=32)
    wall_seconds: int = Field(default=90, ge=1, le=90)


class CampaignBudget(StrictModel):
    model_calls: int = Field(default=6000, ge=1, le=6000)
    tokens: int = Field(default=CAMPAIGN_TOKEN_LIMIT, ge=1, le=CAMPAIGN_TOKEN_LIMIT)
    dollars: float = Field(default=100.0, gt=0, le=100)
    discovery_selections: int = Field(default=8, ge=1, le=8)
    candidates: int = Field(default=4, ge=1, le=4)
    input_tokens_per_call: int = Field(default=MODEL_INPUT_TOKEN_LIMIT, ge=1, le=MODEL_INPUT_TOKEN_LIMIT)
    output_tokens_per_call: int = Field(default=MODEL_OUTPUT_TOKEN_LIMIT, ge=1, le=MODEL_OUTPUT_TOKEN_LIMIT)


class Usage(StrictModel):
    http_attempts: int = Field(default=0, ge=0)
    actor_calls: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    wait_cycles: int = Field(default=0, ge=0)
    ticks: int = Field(default=0, ge=0)
    policy_steps: int = Field(default=0, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0)
    cost_dollars: float | None = Field(default=None, ge=0)


class Provenance(Record):
    campaign_id: Id
    episode_id: Id
    origin: Origin
    split: Split
    arm: Arm
    source_mode: Literal['live', 'replay', 'offline_fixture']
    experiment_purpose: Purpose
    trial_index: int = Field(ge=0, le=2)
    study_id: Id
    evidence_context_id: Id
    selector_id: Literal['explorer', 'systematic', 'random'] | None = None
    execution_epoch: int = Field(ge=0)
    agent_registration_id: Id = 'orders-v1'
    parent_experiment_id: Id | None = None

    @model_validator(mode='after')
    def context_mapping(self):
        purpose = self.experiment_purpose
        expected = ('development', 'prototype') if purpose == 'discovery' else ('promotion', 'faultlab_evaluation') if purpose == 'promotion' else ('final_audit', 'faultlab_evaluation') if purpose in ('final_audit','portability') else ('development','faultlab_evaluation')
        if (self.split, self.origin) != expected:
            raise ValueError('purpose/split/origin mismatch')
        if (purpose == 'selection_comparison') != (self.selector_id is not None):
            raise ValueError('selector identity belongs only to selection comparison')
        return self


class CheckResult(StrictModel):
    check_id: Invariant
    passed: bool
    category: str = Field(max_length=80)
    evidence_ids: list[Id] = Field(default_factory=list, max_length=36)
    event_ids: list[Id] = Field(default_factory=list, max_length=100)


class FaultExecution(StrictModel):
    fault_id: Id
    scheduled: bool = True
    triggered: bool = False
    trigger_tick: int | None = Field(default=None, ge=0, le=25)
    call_id: Id | None = None
    attempt_id: Id | None = None
    reason: Text | None = None


class Verdict(Record):
    verdict_id: Id
    episode_id: Id
    outcome: Outcome
    checks: list[CheckResult] = Field(min_length=8, max_length=8)
    evidence_ids: list[Id] = Field(default_factory=list, max_length=18)
    supported_completion: bool
    useful_resolution: Literal['completed', 'rejected', 'unresolved', 'invalid']
    fault_executions: list[FaultExecution] = Field(default_factory=list, max_length=2)
    upgrade_effects: int = Field(ge=0)
    notification_effects: int = Field(ge=0)
    decision_tick: int = Field(ge=0, le=20)
    horizon_tick: int = Field(ge=0, le=25)
    scorer_hash: Digest

    @model_validator(mode='after')
    def exactly_eight(self):
        if {c.check_id for c in self.checks} != {f'C{i}' for i in range(1,9)}:
            raise ValueError('one result for every C1-C8 required')
        return self


class Event(Record):
    episode_id: Id
    seq: int = Field(ge=1)
    tick: int = Field(ge=0, le=25)
    at: datetime = Field(default_factory=utc_now)
    role: Literal['actor','policy','explorer','mechanic','referee','coordinator','telemetry']
    type: Annotated[str, StringConstraints(max_length=80, pattern=r'^[a-z_]+$')]
    payload: dict = Field(default_factory=dict)
    call_id: Id | None = None
    evidence_id: Id | None = None
    visibility: Literal['PUBLIC_OBSERVATION','DEVELOPMENT_DIAGNOSTIC','PRIVATE_EVALUATOR']


class TrialResult(Record):
    episode_id: Id
    world_id: Id
    scenario_hash: Digest
    policy_hash: Digest
    arm: Arm
    trial_index: int = Field(ge=0, le=2)
    lifecycle: Literal['COMPLETED','INTERRUPTED','LAB_ERROR']
    outcome: Outcome | None
    failed_checks: list[Invariant] = Field(default_factory=list, max_length=8)
    fault_scheduled: bool
    fault_triggered: bool
    usage: Usage = Field(default_factory=Usage)
    reason: Text | None = None


class Counterexample(Record):
    counterexample_id: Id
    campaign_id: Id
    agent_registration_id: Id
    source_episode_id: Id
    target_invariant: Invariant
    scenario_hash: Digest
    configuration_hash: Digest
    report_ref: Id | None
    verdict_ref: Id
    created_at: datetime = Field(default_factory=utc_now)
    reproduction_trial_ids: list[Id] = Field(default_factory=list, max_length=3)
    target_violation_count: int = Field(default=0, ge=0, le=3)
    valid_count: int = Field(default=0, ge=0, le=3)
    attempted_count: int = Field(default=0, ge=0, le=3)
    reproduced: bool = False


class ReductionAttempt(StrictModel):
    transform: Text
    parent_hash: Digest
    child_hash: Digest
    trial_ids: list[Id] = Field(max_length=3)
    retained: bool
    reason: Text


class ReductionResult(Record):
    counterexample_id: Id
    reducer_hash: Digest
    reduction_order: list[Text] = Field(max_length=100)
    original_recipe_hash: Digest
    retained_recipe_hash: Digest | None
    attempts: list[ReductionAttempt] = Field(max_length=24)
    status: Literal['REDUCED','LOCALLY_MINIMAL','FLAKY','INCOMPLETE','NO_REDUCTION']
    valid_count: int = Field(ge=0, le=3)
    attempted_count: int = Field(ge=0, le=3)
    target_violation_count: int = Field(ge=0, le=3)
    stopping_reason: Text
    neighborhood_exhausted: bool


class InterventionExperiment(Record):
    intervention_id: Id
    counterexample_id: Id
    hypothesis: Text
    proposal_ref: Id
    change: Text
    control_hash: Digest
    treatment_hash: Digest
    trial_pairs: list[tuple[Id, Id]] = Field(max_length=3)
    result: Literal['SUPPORTED','CONTRADICTED','INCONCLUSIVE']
    evidence_ids: list[Id] = Field(max_length=108)
    limitations: list[Text] = Field(max_length=16)


class DiagnosticProfile(Record):
    profile_id: Literal['evidence_gap_v1']
    contract_hash: Digest
    capability_hash: Digest
    oracle_hash: Digest
    fixture_hash: Digest
    normalization_hash: Digest
    probe_set: list[Text] = Field(min_length=1, max_length=18)
    horizon: int = Field(ge=1, le=20)
    excluded_from_learning: Literal[True] = True


class DiagnosticResult(Record):
    diagnostic_id: Id
    counterexample_id: Id | None = None
    diagnostic_profile_id: Literal['evidence_gap_v1'] | None = None
    proposed_kind: DiagnosticKind
    kind: DiagnosticKind
    explanation: Text
    intervention_ids: list[Id] = Field(max_length=4)
    reproduction_ids: list[Id] = Field(max_length=3)
    evidence_ids: list[Id] = Field(max_length=108)
    authority_paths: list[Text] = Field(max_length=18)
    equivalence_refs: list[Id] = Field(max_length=18)
    tested_scope: Text
    required_behavior: Text
    limitations: list[Text] = Field(max_length=16)
    checker_hash: Digest
    protocol_hash: Digest

    @model_validator(mode='after')
    def policy_source(self):
        if self.kind == 'POLICY_GAP' and self.counterexample_id is None:
            raise ValueError('POLICY_GAP requires counterexample')
        return self


class ChallengeResult(Record):
    challenge_id: Id
    candidate_hash: Digest
    incumbent_hash: Digest
    source_validation_ref: Id
    schedule_hashes: list[Digest] = Field(max_length=4)
    selection_refs: list[Id] = Field(max_length=8)
    novel_schedule_hashes: list[Digest] = Field(max_length=4)
    trial_pairs: list[tuple[Id,Id]] = Field(max_length=12)
    failed_checks: list[Invariant] = Field(max_length=8)
    status: Literal['PASSED_OBSERVED','COUNTEREXAMPLE_FOUND','INCONCLUSIVE','NOT_RUN']
    stopping_reason: Text

    @model_validator(mode='after')
    def passed_coverage(self):
        if self.status == 'PASSED_OBSERVED' and (len(set(self.schedule_hashes)) != 4 or len(self.trial_pairs) != 12 or not self.novel_schedule_hashes or self.failed_checks):
            raise ValueError('complete four-schedule challenge with novel coverage required')
        return self


class FileEntry(StrictModel):
    path: str = Field(min_length=1, max_length=200)
    sha256: Digest
    size_bytes: int = Field(ge=0, le=10000000)

    @field_validator('path')
    @classmethod
    def relative_path(cls, value):
        if value.startswith(('/', '\\')) or '\\' in value or ':' in value or any(p in ('', '.', '..') for p in value.split('/')):
            raise ValueError('safe relative path required')
        return value


class RegressionBundle(StrictModel):
    export_version: Literal['faultlab-regression/v1'] = 'faultlab-regression/v1'
    bundle_id: Id
    manifest_hash: Digest
    files: list[FileEntry] = Field(min_length=1, max_length=32)
    harness_version: Id
    harness_hash: Digest
    source_recipe: FaultSpec
    retained_recipe: FaultSpec | None
    fixture_id: Literal['standard-v1','history-v1']
    scope: Literal['orders.upgrade_then_confirm/v1'] = SCOPE
    contract_hash: Digest
    capability_hash: Digest
    configuration_hash: Digest
    scorer_hash: Digest
    interpreter_hash: Digest
    policy_hash: Digest
    schema_hash: Digest
    dependency_lock_hash: Digest
    target_invariant: Invariant
    source_refs: list[Id] = Field(max_length=100)
    trial_results: list[TrialResult] = Field(max_length=200)
    registration_requirements: list[Text] = Field(max_length=16)
    execution_profile_id: Id
    caps: EpisodeBudget
    setup_instructions: Text
    created_at: datetime = Field(default_factory=utc_now)


class RegressionExecution(Record):
    execution_id: Id
    bundle_id: Id
    manifest_hash: Digest
    registration_id: Id
    profile_id: Id
    mode: Literal['VALIDATE_ONLY','RECORDED_PLAYBACK','FRESH_SANDBOX']
    explicit_action: bool
    policy_hash: Digest
    configuration_hash: Digest
    declared_budget: EpisodeBudget
    usage: Usage
    episode_ids: list[Id] = Field(max_length=100)
    world_ids: list[Id] = Field(max_length=100)
    status: Literal['PENDING','RUNNING','COMPLETED','INCOMPLETE','REJECTED']
    created_at: datetime = Field(default_factory=utc_now)
    stop_reason: Text | None = None

    @model_validator(mode='after')
    def fresh_action(self):
        if self.mode == 'FRESH_SANDBOX' and not self.explicit_action:
            raise ValueError('fresh execution requires explicit action')
        if self.mode != 'FRESH_SANDBOX' and (self.episode_ids or self.world_ids or self.usage.model_calls or self.usage.http_attempts):
            raise ValueError('validation/playback creates zero effects')
        return self


class AgentRegistration(Record):
    registration_id: Id
    name: Text
    version: Id
    provenance_class: Literal['reference','internal_smoke','external']
    source_origin: str = Field(max_length=500)
    source_owner: Text
    source_revision: Id
    source_hash: Digest
    license: Text
    permission_ref: Text
    adapter_entrypoint_id: Id
    adapter_hash: Digest
    contract_hash: Digest
    capability_hash: Digest
    reset_profile_id: Id
    oracle_hash: Digest
    policy_hooks: list[Hook] = Field(min_length=4,max_length=4)
    model: Text
    prompt_hash: Digest
    configuration_hash: Digest
    dependency_lock_hash: Digest
    budget_compatible: bool
    dry_run_status: Literal['PENDING','PASSED','UNSUPPORTED']
    limitations: list[Text] = Field(max_length=16)


class PortabilityResult(Record):
    portability_id: Id
    source_registration_id: Id
    target_registration_id: Id
    provenance_class: Literal['external','internal_smoke']
    policy_source: Literal['transferred_unchanged','new_target_campaign']
    policy_hash: Digest
    manifest_hash: Digest
    target_configuration_hash: Digest
    trial_pairs: list[tuple[Id,Id]] = Field(max_length=18)
    compatibility_failures: list[Text] = Field(max_length=16)
    status: Literal['PENDING','COMPLETED','INCOMPLETE','UNSUPPORTED']
    limitations: list[Text] = Field(max_length=16)


class SearchComparison(Record):
    comparison_id: Id
    status: Literal['PENDING','RUNNING','COMPLETED','INCOMPLETE']
    campaign_id: Id
    manifest_hash: Digest
    registration_id: Id
    policy_hash: Digest
    generator_hash: Digest
    validator_hash: Digest
    deduplication_hash: Digest
    selector_order: list[Literal['explorer','systematic']] = Field(min_length=2,max_length=2)
    systematic_digest: Digest
    context_ids: list[Id] = Field(min_length=2,max_length=2)
    trial_ids: list[Id] = Field(max_length=48)
    usage: Usage
    stopping_reason: Text


class CampaignRequest(StrictModel):
    task_text: str = Field(min_length=1,max_length=2000)
    order_id: Id
    mode: Literal['baseline','learn','compare']
    config_profile_id: Id = 'offline-v1'


class Campaign(Record):
    campaign_id: Id
    mode: Literal['baseline','learn','compare']
    state: CampaignState = 'IDLE'
    state_seq: int = Field(default=0,ge=0)
    execution_epoch: int = Field(default=0,ge=0)
    task_text: str = Field(max_length=2000)
    order_id: Id
    config_profile_id: Id
    model: Text
    configuration_hash: Digest
    active_policy_version: Id = 'policy-v0'
    latest_episode_id: Id | None = None
    stop_requested: bool = False
    caps: CampaignBudget = Field(default_factory=CampaignBudget)
    usage: Usage = Field(default_factory=Usage)
    reserved_calls: int = Field(default=1064, ge=0)
    telemetry_status: Literal['local_recorded','weave_pending','weave_verified','weave_error'] = 'local_recorded'
    aria_status: Literal['PENDING','UNVERIFIED','COMPLETED','FAILED'] = 'PENDING'
    terminal_reason: Text | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Episode(Provenance):
    world_id: Id
    task_id: Id
    scenario_hash: Digest
    policy_hash: Digest
    policy_version: Id
    model: Text
    configuration_hash: Digest
    lifecycle: Literal['CREATED','RUNNING','SCORING','COMPLETED','INTERRUPTED','LAB_ERROR'] = 'CREATED'
    report: TaskReport | None = None
    verdict: Verdict | None = None
    usage: Usage = Field(default_factory=Usage)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    reason: Text | None = None


class PolicyVersion(Record):
    version: Id
    parent_version: Id | None
    content: RecoveryPolicy | None
    policy_hash: Digest | None
    author: Literal['mechanic','manual','baseline']
    raw_proposal_ref: Id | None
    development_episode_ids: list[Id] = Field(max_length=200)
    decision: Literal['BASELINE','PROPOSED','ACCEPTED','REJECTED','NO_CHANGE','INCOMPLETE']
    decision_ref: Id | None = None
    evaluation_refs: list[Id] = Field(default_factory=list,max_length=20)
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceBundle(Record):
    episode_id: Id
    policy_hash: Digest
    contract_hash: Digest
    scorer_hash: Digest
    source: Literal['weave_verified','local_only']
    root_call_id: Id | None
    child_call_ids: list[Id] = Field(max_length=100)
    observations: list[PublicObservation] = Field(max_length=18)
    report: TaskReport | None
    findings: list[CheckResult] = Field(max_length=8)
    retrieved_at: datetime | None
    digest: Digest
    source_project: Text | None


class EvaluationBatch(Record):
    batch_id: Id
    purpose: Purpose
    split: Split
    candidate_hash: Digest
    incumbent_hash: Digest
    manifest_hash: Digest
    scorer_hash: Digest
    contract_hash: Digest
    model_hash: Digest
    trial_pairs: list[tuple[Id,Id]] = Field(max_length=100)
    trials: list[TrialResult] = Field(max_length=200)
    usage: Usage
    decision: Literal['ACCEPTED','REJECTED','NO_CHANGE','INCOMPLETE']
    reason: Text


class AriaAnalysis(Record):
    analysis_id: Id
    campaign_id: Id
    run_id: Id
    automation_id: Id
    invocation_mode: Literal['automatic','manual']
    provenance: Literal['manual_ui_capture']
    status: Literal['PENDING','UNVERIFIED','COMPLETED','FAILED']
    execution_id: Id | None
    observed_at: datetime
    thread_id: Id | None
    history_url: str | None = Field(max_length=1000)
    output_url: str | None = Field(max_length=1000)
    summary: Text
    recorder: Text
    verified_source_refs: list[Id] = Field(max_length=100)


class Operation(Record):
    operation_id: Id
    service: Service
    task_id: Id
    order_id: Id
    payload_hash: Digest
    state: StoredStatus
    accepted_tick: int = Field(ge=0,le=20)
    terminal_tick: int | None = Field(default=None,ge=0,le=25)
    receipt: Receipt | None = None


class NotificationEffect(Record):
    notification_id: Id
    order_id: Id
    upgrade_operation_id: Id
    operation_id: Id
    idempotency_key: Id
    payload_hash: Digest
    created_tick: int = Field(ge=0,le=25)
    template_version: Literal['confirmation/v1'] = 'confirmation/v1'


class IdempotencyRecord(Record):
    service: Service
    key: Id
    payload_hash: Digest
    operation_id: Id


class OperationJournal(Record):
    episode_id: Id
    operation_id: Id
    service: Service
    intent_hash: Digest
    payload_hash: Digest
    original_request: str = Field(max_length=4000)
    attempt_ids: list[Id] = Field(max_length=18)
    latest_status: Status | None
    terminal_receipt_id: Id | None


class ToolCallRecord(Record):
    call_id: Id
    episode_id: Id
    tool: Tool
    caller: Literal['actor','policy']
    hook: Hook | None
    attempt_ids: list[Id] = Field(max_length=18)
    observation_ids: list[Id] = Field(max_length=18)
    usage: Usage


class WorldSnapshot(Record):
    world_id: Id
    tick: int = Field(ge=0,le=25)
    orders: list[Order] = Field(max_length=10)
    operations: list[Operation] = Field(max_length=2)
    notifications: list[NotificationEffect] = Field(max_length=18)
    events: list[Event] = Field(max_length=300)


class RegressionCase(Record):
    regression_id: Id
    campaign_id: Id
    counterexample_id: Id
    target_invariant: Invariant
    scope: Literal['orders.upgrade_then_confirm/v1'] = SCOPE
    first_failing_policy: Id
    accepted_policy: Id | None
    reduction_ref: Id | None
    diagnostic_ref: Id | None
    challenge_ref: Id | None
    bundle_id: Id | None


class WeaveIngestion(Record):
    ingestion_id: Id
    episode_id: Id
    source_project: Text
    root_call_id: Id
    origin: Origin
    state: Literal['PENDING','FETCHING','INGESTED','RETRYABLE_ERROR','REJECTED']
    evidence_digest: Digest | None
    execution_epoch: int = Field(ge=0)
    reason: Text | None


class TelemetryOutbox(Record):
    outbox_id: Id
    payload_digest: Digest
    record_kind: Literal['trace','evaluation','dataset','campaign']
    record_ref: Id
    state: Literal['PENDING','UPLOADING','VERIFIED','ERROR']
    attempts: int = Field(ge=0)
    remote_ref: Text | None
    error_code: Text | None
