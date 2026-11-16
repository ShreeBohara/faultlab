"""The bookings checks H1 to H8 behind the v2 ``Referee`` protocol.

The fixed checks are the September pack's own (``taskpacks/bookings_move_with_hold/checks.py``). This module
rebuilds their inputs from v2 evidence: the session's observations in the September form with the world's ids
put back where the agent saw hold labels, the report with its labels turned back into ids, the lab's scope
refusals, usage against the September budget (narrowed by the plan's caps), the world's decision and horizon
snapshots, and the September world-integrity comparisons. It refuses to score with a checker whose sha256 is not
the one the plan pinned, and a pack other than bookings.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from faultlab.core.errors import IntegrityError
from faultlab.evidence.legacy import TASK_BY_OUTCOME
from faultlab.evidence.models import Finding, TrialEnvelope
from faultlab.lab.worker import ScoringContext, Verdict
from faultlab.packs.bookings.pack import PACK
from faultlab.packs.bookings.views import september_observations, swap_references
from taskpacks.bookings_move_with_hold import checks, driver, table

PACK_ID = PACK.pack_id
CHECKER = Path(checks.__file__)


def checker_digest() -> str:
    return sha256(CHECKER.read_bytes()).hexdigest()


def labels_of(envelope: TrialEnvelope) -> dict[str, str]:
    """Which world id each hold label stood for, from the lab's own records (evaluator plane)."""
    return {event.payload["label"]: event.payload["id"] for event in envelope.events
            if event.kind == "reference_labelled" and isinstance(event.payload, dict)
            and isinstance(event.payload.get("label"), str) and isinstance(event.payload.get("id"), str)}


class BookingsReferee:
    """Scores a bookings trial with H1 to H8; ``property_version`` is the checker's digest."""

    def __init__(self, *, require_digest: bool = True):
        self.require_digest = require_digest

    def score(self, envelope: TrialEnvelope, context: ScoringContext) -> Verdict:
        if envelope.plan.pack_id != PACK_ID:
            raise IntegrityError(f"The bookings referee scores {PACK_ID} only")
        if context.decision is None or context.horizon is None:
            raise IntegrityError("The bookings referee needs the decision and horizon snapshots")
        digest = checker_digest()
        pinned = envelope.plan.properties_digest
        if self.require_digest and pinned is not None and digest != pinned:
            raise IntegrityError("The checker that ran is not the checker the plan pinned")
        real_of = labels_of(envelope)
        calls = envelope.source_facts.get("calls") or []
        observations = september_observations(context.observations, calls, real_of=real_of)
        report = None
        if envelope.report.status == "DELIVERED" and isinstance(envelope.report.interpreted, dict):
            report = swap_references(envelope.report.interpreted, "hold_id", real_of)
            report["open_hold_ids"] = [real_of.get(hold, hold) for hold in report.get("open_hold_ids", [])]
        lab_events = []
        for event in envelope.events:
            if event.kind == "scope_refusal" and isinstance(event.payload, dict):
                shown = event.payload.get("observation") or {}
                reference = event.payload.get("reference")
                lab_events.append({"seq": len(lab_events) + 1, "type": "scope_refusal",
                                   "payload": {"tool": shown.get("tool"), "hold_id": real_of.get(reference, reference),
                                               "call_id": shown.get("call_id"), "caller": "actor"}})
        usage = context.usage
        september_usage = {"http_attempts": int(usage.get("http_attempts", 0)), "actor_calls": int(usage.get("model_calls", 0)),
                           "wait_cycles": int(usage.get("waits", 0)), "ticks": int(usage.get("ticks", 0)),
                           "policy_steps": sum(1 for event in envelope.events if event.kind == "rule_step"),
                           "wall_seconds": float(envelope.outcome.cost.wall_seconds)}
        budget = dict(table.DEFAULT_BUDGET)
        caps = envelope.plan.caps
        for key, cap in (("http_attempts", caps.http_attempts), ("actor_calls", caps.model_calls), ("ticks", caps.ticks),
                         ("wall_seconds", caps.wall_seconds)):
            if cap is not None:
                budget[key] = min(budget[key], cap)
        integrity = driver.world_integrity(context.decision, context.horizon, september_usage,
                                           [{"attempt_ids": call.get("attempt_ids") or []} for call in calls])
        if context.execution == "INFRA_ERROR":
            integrity = {**integrity, "status": "INVALID", "issues": [*integrity["issues"], "INFRA_ERROR"]}
        intent = {**{key: value for key, value in context.intent.items() if key != "task_text"}, "task_definition_id": PACK_ID}
        verdict = checks.score(intent=intent, report=report, observations=observations, decision=context.decision,
                               horizon=context.horizon, lab_events=lab_events, usage=september_usage, budget=budget,
                               world_integrity=integrity)
        specs = {spec.property_id: spec for spec in PACK.properties.properties}
        findings = [Finding(property_id=check["id"], property_version=digest, result="PASS" if check["passed"] else "VIOLATION",
                            family=specs[check["id"]].family, severity=specs[check["id"]].severity,
                            note=", ".join(check["reasons"])[:2000]) for check in verdict["checks"]]
        task = TASK_BY_OUTCOME.get(verdict["outcome"])
        note = verdict["harm_sentence"] if task is not None else f"bookings outcome {verdict['outcome']}: {verdict['harm_sentence']}"
        return Verdict(task=task, findings=findings, note=note[:600])


__all__ = ["BookingsReferee", "PACK_ID", "checker_digest", "labels_of"]
