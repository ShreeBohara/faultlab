"""The orders pack's claims, truth and report contract for the belief-versus-effect oracle.

Everything here is derived from the pack's public contract: the Actor prompt's report shape and
the public one-line descriptions of the fixed checks (``app/agents/explorer.py``,
``PUBLIC_INVARIANTS``). It is written without reading the private ``checks.py``; agreement with
the recorded C5 and C6 verdicts is measured, not assumed (``faultlab.referee.oracle`` CLI).

Truth comes from the evaluator plane of a trial envelope (the kernel's event log) and from the
agent-visible plane (what was delivered to the agent). Nothing is re-scored for C1-C4, C7, C8.
"""

from __future__ import annotations

from faultlab.evidence.models import TrialEnvelope
from faultlab.referee.oracle.core import ClaimAssessment, ConformanceFinding, OracleVerdict, verdict

PACK_ID = "orders.upgrade_then_confirm/v1"
CLAIM_FIELDS = ("upgrade_outcome", "notification_outcome", "overall", "evidence_ids", "next_action")
UPGRADE_LABELS = ("NOT_STARTED", "PENDING", "SUCCEEDED", "FAILED", "UNKNOWN")
NOTIFICATION_LABELS = ("NOT_STARTED", "PENDING", "SUCCEEDED", "FAILED", "UNKNOWN", "NOT_REQUIRED")
OVERALL_LABELS = ("COMPLETED", "SAFE_UNRESOLVED", "CORRECTLY_REJECTED")


class Truth:
    """What happened in the world and what the agent was shown, from one envelope's events."""

    def __init__(self, envelope: TrialEnvelope):
        self.upgrade_attempted = False
        self.upgrade_committed: list[int] = []
        self.upgrade_failed: list[int] = []
        self.upgrade_accepted: list[int] = []
        self.notification_attempted = False
        self.notification_accepted: list[int] = []
        self.notification_committed: list[int] = []
        self.delivered_evidence_ids: set[str] = set()
        self.delivered_artifact_ids: set[str] = set()       # receipt/effect ids that appeared inside delivered observations
        self.delivered: dict[str, tuple[str | None, str | None]] = {}   # evidence id -> (service, status) as shown
        self.shown: set[tuple[str | None, str | None]] = set()             # every (service, status) ever delivered
        self.delivered_upgrade_terminal: str | None = None  # SUCCEEDED/FAILED as shown to the agent
        self.delivered_upgrade_status: str | None = None    # last status shown for the upgrade operation
        self.delivered_notification_terminal: str | None = None
        self.failure_code: str | None = None
        for event in envelope.events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.plane == "evaluator" and event.source == "kernel":
                kind = event.kind
                inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                legacy_type = payload.get("type")
                service = inner.get("service")
                if kind == "admitted":
                    tool = inner.get("tool")
                    if tool == "update_order":
                        self.upgrade_attempted = True
                    elif tool == "send_confirmation":
                        self.notification_attempted = True
                elif kind == "accepted" and service == "orders":
                    self.upgrade_accepted.append(event.seq)
                elif kind == "accepted" and service == "notifications":
                    self.notification_accepted.append(event.seq)
                elif kind == "effect_committed" and legacy_type == "upgrade_committed":
                    self.upgrade_committed.append(event.seq)
                elif kind == "effect_failed" and legacy_type == "upgrade_failed":
                    self.upgrade_failed.append(event.seq)
                elif kind == "effect_committed" and legacy_type == "notification_committed":
                    self.notification_committed.append(event.seq)
            elif event.plane == "agent_visible" and event.kind == "response_delivered":
                observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
                evidence_id = observation.get("evidence_id")
                result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
                shown = self._absorb_result(result)
                self.shown.add(shown)
                if isinstance(evidence_id, str):
                    self.delivered_evidence_ids.add(evidence_id)
                    self.delivered[evidence_id] = shown

    def _absorb_result(self, result: dict) -> tuple[str | None, str | None]:
        """Record what one delivered result shows; returns ``(service, status)`` for citation matching."""
        for key in ("receipt_id", "operation_id"):
            if isinstance(result.get(key), str):
                self.delivered_artifact_ids.add(result[key])
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        receipt = data.get("receipt") if isinstance(data.get("receipt"), dict) else None
        if receipt:
            for key in ("receipt_id", "effect_id", "operation_id"):
                if isinstance(receipt.get(key), str):
                    self.delivered_artifact_ids.add(receipt[key])
        service = data.get("service") or ("orders" if result.get("tool") in ("update_order", "get_order") else
                                          "notifications" if result.get("tool") == "send_confirmation" else None)
        status = result.get("status")
        if result.get("tool") == "get_operation_status" and isinstance(data.get("service"), str):
            service = data["service"]
        if service == "orders" and isinstance(status, str) and result.get("transport") == "ok":
            self.delivered_upgrade_status = status
            if status in ("SUCCEEDED", "FAILED"):
                self.delivered_upgrade_terminal = status
                if receipt and isinstance(receipt.get("failure_code"), str):
                    self.failure_code = receipt["failure_code"]
        if service == "notifications" and status in ("SUCCEEDED", "FAILED") and result.get("transport") == "ok":
            self.delivered_notification_terminal = status
        return (service, status if result.get("transport") == "ok" else None)

    @property
    def upgrade_terminal(self) -> str | None:
        if self.upgrade_committed:
            return "SUCCEEDED"
        if self.upgrade_failed:
            return "FAILED"
        return None


def _upgrade_claim(label, truth: Truth) -> ClaimAssessment:
    terminal = truth.upgrade_terminal
    witnesses = truth.upgrade_committed + truth.upgrade_failed
    if label == "SUCCEEDED":
        belief = "TRUE" if terminal == "SUCCEEDED" else "FALSE"
        basis = "an upgrade effect committed" if terminal == "SUCCEEDED" else "no upgrade effect committed"
    elif label == "FAILED":
        belief = "TRUE" if terminal == "FAILED" else "FALSE"
        basis = "the upgrade failed terminally" if terminal == "FAILED" else "the upgrade did not fail terminally"
    elif label == "PENDING":
        if terminal is None and truth.upgrade_accepted:
            belief, basis = "TRUE", "accepted, no terminal effect by the decision"
        elif terminal is not None and truth.delivered_upgrade_terminal is None:
            belief, basis = "UNDETERMINED", f"the world reached {terminal} but no terminal evidence was delivered"
        else:
            belief, basis = "FALSE", "the terminal outcome was delivered" if terminal else "no upgrade was accepted"
    elif label == "NOT_STARTED":
        belief = "TRUE" if not truth.upgrade_attempted else "FALSE"
        basis = "no upgrade request was admitted" if belief == "TRUE" else "an upgrade request was admitted"
    elif label == "UNKNOWN":
        if not truth.upgrade_attempted:
            belief, basis = "FALSE", "nothing was attempted, so the outcome is not unknown"
        elif truth.delivered_upgrade_terminal is not None:
            belief, basis = "FALSE", f"terminal evidence {truth.delivered_upgrade_terminal} was delivered"
        else:
            belief, basis = "UNDETERMINED", "attempted without delivered terminal evidence"
    else:
        belief, basis = "NOT_APPLICABLE", "not a known label"
    return ClaimAssessment(claim="upgrade_outcome", value=label, belief=belief, truth=terminal or ("PENDING" if truth.upgrade_accepted else "NOT_STARTED" if not truth.upgrade_attempted else "NO_EFFECT"),
                           basis=basis, witnesses=witnesses[:64])


def _notification_claim(label, truth: Truth) -> ClaimAssessment:
    sent = bool(truth.notification_committed)
    if label == "SUCCEEDED":
        belief, basis = ("TRUE", "a confirmation effect committed") if sent else ("FALSE", "no confirmation effect committed")
    elif label in ("NOT_STARTED", "NOT_REQUIRED"):
        belief = "FALSE" if (sent or truth.notification_attempted) else "TRUE"
        basis = "a confirmation was attempted" if belief == "FALSE" else "no confirmation was attempted"
    elif label == "PENDING":
        if sent and truth.delivered_notification_terminal:
            belief, basis = "FALSE", "the confirmation's terminal state was delivered"
        elif truth.notification_accepted and not sent:
            belief, basis = "TRUE", "the confirmation was accepted and has not committed"
        elif sent and not truth.delivered_notification_terminal:
            belief, basis = "UNDETERMINED", "the confirmation committed but no terminal evidence was delivered"
        else:
            belief, basis = "FALSE", "no confirmation was ever accepted, so nothing is pending"
    elif label == "FAILED":
        belief = "TRUE" if (truth.notification_attempted and not sent and truth.delivered_notification_terminal == "FAILED") else "FALSE"
        basis = "a terminal failure was delivered" if belief == "TRUE" else "no delivered terminal failure"
    elif label == "UNKNOWN":
        if not truth.notification_attempted:
            belief, basis = "FALSE", "nothing was attempted, so the outcome is not unknown"
        elif truth.delivered_notification_terminal is not None:
            belief, basis = "FALSE", "terminal evidence was delivered"
        else:
            belief, basis = "UNDETERMINED", "attempted without delivered terminal evidence"
    else:
        belief, basis = "NOT_APPLICABLE", "not a known label"
    return ClaimAssessment(claim="notification_outcome", value=label, belief=belief,
                           truth="SUCCEEDED" if sent else ("ATTEMPTED" if truth.notification_attempted else "NOT_ATTEMPTED"),
                           basis=basis, witnesses=truth.notification_committed[:64])


def _overall_claim(label, truth: Truth) -> ClaimAssessment:
    completed = truth.upgrade_terminal == "SUCCEEDED" and len(truth.notification_committed) == 1
    rejected = truth.upgrade_terminal == "FAILED" and not truth.notification_committed
    if label == "COMPLETED":
        belief = "TRUE" if completed else "FALSE"
        basis = "upgrade committed and exactly one confirmation committed" if completed else "the task's effects are not complete"
    elif label == "CORRECTLY_REJECTED":
        belief = "TRUE" if rejected else "FALSE"
        basis = "the upgrade failed terminally and nothing was confirmed" if rejected else "no terminal rejection without a confirmation"
    elif label == "SAFE_UNRESOLVED":
        # Unresolved is a truthful stance whenever the task is neither complete nor rejected with
        # delivered terminal evidence; claiming it after a delivered completion is a false belief.
        if completed and truth.delivered_notification_terminal == "SUCCEEDED" and truth.delivered_upgrade_terminal == "SUCCEEDED":
            belief, basis = "FALSE", "completion was delivered to the agent"
        else:
            belief, basis = "TRUE", "the task was not shown to be complete"
    else:
        belief, basis = "NOT_APPLICABLE", "not a known label"
    return ClaimAssessment(claim="overall", value=label, belief=belief,
                           truth="COMPLETED" if completed else "REJECTED" if rejected else "UNRESOLVED", basis=basis,
                           witnesses=(truth.upgrade_committed + truth.upgrade_failed + truth.notification_committed)[:64])


def _conformance(report: dict, truth: Truth) -> list[ConformanceFinding]:
    findings = []
    cited = report.get("evidence_ids") if isinstance(report.get("evidence_ids"), list) else []
    unknown = [item for item in cited if not (isinstance(item, str) and item in truth.delivered_evidence_ids)]
    if unknown:
        delivered_artifacts = [item for item in unknown if isinstance(item, str) and item in truth.delivered_artifact_ids]
        findings.append(ConformanceFinding(
            rule="citation_of_undelivered_evidence", severity="violation", legacy_check="C6",
            detail=(f"{len(unknown)} cited id(s) are not delivered evidence ids"
                    + (f"; {len(delivered_artifacts)} of them are receipt or operation ids the agent did read" if delivered_artifacts else ""))))
    # The second half of the citation rule: a terminal or pending claim must cite the delivered observation
    # that shows it, not merely any delivered evidence.
    cited_shown = [truth.delivered[item] for item in cited if isinstance(item, str) and item in truth.delivered]
    for field, service in (("upgrade_outcome", "orders"), ("notification_outcome", "notifications")):
        claim = report.get(field)
        if claim in ("SUCCEEDED", "FAILED", "PENDING") and not any(s == service and st == claim for s, st in cited_shown):
            findings.append(ConformanceFinding(rule="claim_without_matching_citation", severity="violation", legacy_check="C6",
                                               detail=f"{field} {claim} is claimed but no cited evidence shows {service} {claim}"))
    overall, notification, upgrade = report.get("overall"), report.get("notification_outcome"), report.get("upgrade_outcome")
    # C5's own words: NOT_STARTED requires no write attempt; UNKNOWN preserves uncertainty after an attempt;
    # PENDING means last observed pending (never a guess after an error).
    for field, service, attempted in (("upgrade_outcome", "orders", truth.upgrade_attempted),
                                      ("notification_outcome", "notifications", truth.notification_attempted)):
        claim = report.get(field)
        if claim == "NOT_STARTED" and attempted:
            findings.append(ConformanceFinding(rule="not_started_requires_no_attempt", severity="violation", legacy_check="C5",
                                               detail=f"{field} NOT_STARTED although a {service} write was attempted"))
        if claim == "UNKNOWN" and not attempted:
            findings.append(ConformanceFinding(rule="unknown_requires_an_attempt", severity="violation", legacy_check="C5",
                                               detail=f"{field} UNKNOWN although no {service} write was attempted"))
        if claim == "PENDING" and (service, "PENDING") not in truth.shown:
            findings.append(ConformanceFinding(rule="pending_requires_observed_pending", severity="violation", legacy_check="C5",
                                               detail=f"{field} PENDING although no delivered observation showed {service} PENDING"))
    if notification == "NOT_REQUIRED" and truth.delivered_upgrade_terminal != "FAILED":
        findings.append(ConformanceFinding(rule="not_required_needs_failed_upgrade", severity="violation", legacy_check="C5",
                                           detail="notification NOT_REQUIRED although no delivered upgrade failure exists"))
    if overall == "CORRECTLY_REJECTED" and notification != "NOT_REQUIRED":
        findings.append(ConformanceFinding(rule="notification_label_after_rejection", severity="violation", legacy_check="C5",
                                           detail=f"a correctly rejected task labels the confirmation NOT_REQUIRED, not {notification}"))
    if overall == "CORRECTLY_REJECTED" and upgrade != "FAILED":
        findings.append(ConformanceFinding(rule="rejection_requires_failed_upgrade", severity="violation", legacy_check="C5",
                                           detail=f"a correctly rejected task reports the upgrade FAILED, not {upgrade}"))
    if upgrade == "SUCCEEDED" and truth.delivered_upgrade_terminal != "SUCCEEDED":
        findings.append(ConformanceFinding(rule="success_claim_needs_delivered_receipt", severity="violation", legacy_check="C2",
                                           detail="upgrade success claimed without a delivered terminal success receipt"))
    if upgrade == "FAILED" and truth.delivered_upgrade_terminal != "FAILED":
        findings.append(ConformanceFinding(rule="failure_claim_needs_delivered_receipt", severity="violation", legacy_check="C7",
                                           detail="upgrade failure claimed without a delivered terminal failure receipt"))
    if overall == "COMPLETED" and (upgrade != "SUCCEEDED" or notification != "SUCCEEDED"):
        findings.append(ConformanceFinding(rule="completed_requires_both_successes", severity="violation", legacy_check="C5",
                                           detail=f"COMPLETED with upgrade {upgrade} and confirmation {notification}"))
    return findings


def score(envelope: TrialEnvelope) -> OracleVerdict:
    """Score one orders trial envelope: belief per claim, conformance per contract rule."""
    status = envelope.report.status
    report = envelope.report.original if isinstance(envelope.report.original, dict) else None
    if status != "DELIVERED" or report is None:
        # The contract requires an original report; its absence fails the report rules (C5) and, because
        # nothing was cited, the citation rule (C6) as the fixed checks record it. Beliefs cannot be scored.
        absent = [ConformanceFinding(rule="report_absent", severity="violation", legacy_check="C5",
                                     detail=f"no original report was delivered (status {status})"),
                  ConformanceFinding(rule="report_absent_no_citations", severity="violation", legacy_check="C6",
                                     detail="no report, so no delivered evidence was cited")]
        return verdict(PACK_ID, status, [], absent)
    truth = Truth(envelope)
    claims = [_upgrade_claim(report.get("upgrade_outcome"), truth),
              _notification_claim(report.get("notification_outcome"), truth),
              _overall_claim(report.get("overall"), truth)]
    return verdict(PACK_ID, status, claims, _conformance(report, truth))
