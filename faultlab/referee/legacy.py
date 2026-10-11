"""The legacy orders referee behind the v2 ``Referee`` protocol: the strangler seam for scoring.

The fixed checks C1 to C8 of the orders pack live in ``backend/app/referee/checks.py`` and stay
there until a later phase moves them. This module runs them as a black box on v2 evidence: the
sealed draft envelope plus the worker's scoring context (the trial's intent, what the agent was
shown, the world's decision and horizon snapshots, the kernel's fault records, usage). It never
reads the checker; it calls it, and it refuses to use a checker whose digest is not the one the
plan pinned. The only module in ``faultlab`` that imports the legacy ``app`` package, lazily and
on purpose, so the dependency is visible in one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from faultlab.core.canonical import canonical_json
from faultlab.core.errors import IntegrityError
from faultlab.evidence.legacy import CHECK_FAMILIES, TASK_BY_OUTCOME
from faultlab.evidence.models import Finding, TrialEnvelope
from faultlab.lab.worker import ScoringContext, Verdict

PACK_ID = "orders.upgrade_then_confirm/v1"


def _legacy():
    try:
        from app.contracts import models
        from app.referee import checks
    except ImportError:
        # Running from the repository (python -m faultlab): the legacy package lives under backend/.
        import sys
        backend = Path(__file__).resolve().parents[2] / "backend"
        if not (backend / "app" / "referee").is_dir():
            raise IntegrityError("The legacy orders referee is unavailable: no backend/app beside this package") from None
        if str(backend) not in sys.path:
            sys.path.append(str(backend))
        try:
            from app.contracts import models
            from app.referee import checks
        except ImportError as error:                  # the legacy backend cannot be imported: no scoring, no guess
            raise IntegrityError(f"The legacy orders referee is unavailable: {error}") from error
    return models, checks


def witnesses_by_evidence_id(envelope: TrialEnvelope) -> dict[str, int]:
    """Event seq of the delivery of every evidence id the agent was shown."""
    table: dict[str, int] = {}
    for event in envelope.events:
        if event.plane == "agent_visible" and event.kind == "response_delivered" and isinstance(event.payload, dict):
            observation = event.payload.get("observation")
            if isinstance(observation, dict) and isinstance(observation.get("evidence_id"), str):
                table[observation["evidence_id"]] = event.seq
    return table


class LegacyOrdersReferee:
    """Scores an orders trial with the legacy fixed checks; ``property_version`` is the checker's digest."""

    def __init__(self, *, require_digest: bool = True):
        self.require_digest = require_digest

    def score(self, envelope: TrialEnvelope, context: ScoringContext) -> Verdict:
        if envelope.plan.pack_id != PACK_ID:
            raise IntegrityError(f"The legacy orders referee scores {PACK_ID} only")
        if context.decision is None or context.horizon is None:
            raise IntegrityError("The legacy referee needs the decision and horizon snapshots")
        models, checks = _legacy()
        intent = models.TaskIntent.model_validate(context.intent)
        report = None
        if envelope.report.status == "DELIVERED" and envelope.report.interpreted is not None:
            report = models.TaskReport.model_validate(envelope.report.interpreted)
        observations = [self._observation(models, item, envelope.attempt.attempt_id) for item in context.observations]
        # JSON validation, as the legacy world client did: the snapshot's timestamps arrive as text.
        decision = models.WorldSnapshot.model_validate_json(canonical_json(context.decision))
        horizon = models.WorldSnapshot.model_validate_json(canonical_json(context.horizon))
        usage = context.usage
        legacy_usage = models.Usage(http_attempts=int(usage.get("http_attempts", 0)), actor_calls=int(usage.get("model_calls", 0)),
                                    model_calls=int(usage.get("model_calls", 0)), input_tokens=int(usage.get("input_tokens", 0)),
                                    output_tokens=int(usage.get("output_tokens", 0)), wait_cycles=int(usage.get("waits", 0)),
                                    ticks=int(usage.get("ticks", 0)), wall_seconds=float(envelope.outcome.cost.wall_seconds),
                                    cost_dollars=usage.get("dollars_measured"))
        faults = [models.FaultExecution.model_validate(record) for record in context.fault_executions]
        verdict = checks.score(intent, report, observations, decision, horizon, episode_id=envelope.attempt.attempt_id,
                               usage=legacy_usage, fault_executions=faults, lab_error=context.execution == "INFRA_ERROR",
                               stopped=context.execution == "STOPPED")
        pinned = envelope.plan.properties_digest
        if self.require_digest and pinned is not None and verdict.scorer_hash != pinned:
            raise IntegrityError("The checker that ran is not the checker the plan pinned")
        seqs = witnesses_by_evidence_id(envelope)
        findings = []
        for check in verdict.checks:
            family, severity = CHECK_FAMILIES.get(check.check_id, ("unknown_property", "major"))
            findings.append(Finding(property_id=check.check_id, property_version=verdict.scorer_hash,
                                    result="PASS" if check.passed else "VIOLATION", family=family, severity=severity,
                                    witnesses=sorted({seqs[e] for e in check.evidence_ids if e in seqs}), note=str(check.category)[:2000]))
        task = TASK_BY_OUTCOME.get(verdict.outcome)
        note = "" if task is not None else f"legacy outcome {verdict.outcome}"
        return Verdict(task=task, findings=findings, note=note)

    @staticmethod
    def _observation(models, item: dict[str, Any], episode_id: str):
        result = models.ToolResult.model_validate(item["result"])
        data = result.data
        return models.PublicObservation(evidence_id=item["evidence_id"], episode_id=episode_id, call_id=item["call_id"],
                                        delivered_tick=min(int(item["delivered_tick"]), 20), result=result,
                                        observed_operation_id=getattr(data, "operation_id", None),
                                        observed_order_id=getattr(data, "order_id", None),
                                        observed_intent_hash=getattr(data, "intent_hash", None), source_receipt_id=result.receipt_id)


__all__ = ["LegacyOrdersReferee", "PACK_ID", "witnesses_by_evidence_id"]
