"""Bounded retrieval of a registered development episode, never arbitrary queries."""

import asyncio
from dataclasses import dataclass, field
import time
from typing import Callable

from app.telemetry.safety import TelemetryError, digest, public_json, utc_now


@dataclass(frozen=True)
class TraceRegistration:
    project: str
    metadata: dict
    root_call_id: str
    child_call_ids: tuple[str, ...] = ()
    child_identities: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceReadResult:
    status: str
    ingestion_state: str
    snapshot: dict | None = None
    error_code: str | None = None


class WeaveReader:
    def __init__(self, worker, project: str, authorize: Callable[[TraceRegistration], bool], *,
                 deadline_seconds: float = 60, poll_seconds: float = 2,
                 clock=time.monotonic, sleep=asyncio.sleep):
        if not 0 < deadline_seconds <= 60 or not 0 < poll_seconds <= 2:
            raise TelemetryError("Invalid evidence timing limits.")
        self.worker, self.project, self.authorize = worker, project, authorize
        self.deadline_seconds, self.poll_seconds = deadline_seconds, poll_seconds
        self.clock, self.sleep = clock, sleep

    def _authorized(self, registration):
        ids = (registration.root_call_id, *registration.child_call_ids)
        if (registration.project != self.project or registration.metadata.get("split") != "development"
                or registration.metadata.get("source_mode") != "live" or not all(ids)
                or len(ids) > 19 or len(set(ids)) != len(ids) or not self.authorize(registration)):
            raise TelemetryError("Episode evidence is not authorized.")

    def _normalize(self, registration, calls):
        expected = (registration.root_call_id, *registration.child_call_ids)
        records = {}
        for call in calls:
            call = public_json(call)
            call_id = call.get("id")
            if call_id not in expected or call_id in records:
                raise TelemetryError("Unexpected or duplicate remote call.")
            if call.get("project_id") != self.project:
                raise TelemetryError("Remote project mismatch.")
            attributes = call.get("attributes") or {}
            if any(attributes.get(k) != v for k, v in registration.metadata.items()):
                raise TelemetryError("Remote episode correlation mismatch.")
            identity = registration.child_identities.get(call_id, {})
            if any(attributes.get(k) != v for k, v in identity.items()):
                raise TelemetryError("Remote public observation identity mismatch.")
            if not call.get("ended_at") or call.get("output") is None:
                return None
            if call.get("exception"):
                raise TelemetryError("Remote call contains an unsanitized exception.")
            if not isinstance(call.get("inputs"), dict) or not isinstance(call.get("output"), dict):
                raise TelemetryError("Required public call input/output fields are missing.")
            records[call_id] = call
        if set(records) != set(expected):
            return None
        root = records[registration.root_call_id]
        if ("terminal_status" not in root["output"] or "report" not in root["output"]
                or root["output"]["terminal_status"] == "TELEMETRY_REJECTED"):
            raise TelemetryError("Root public report/completion is missing.")
        for call_id in registration.child_call_ids:
            child = records[call_id]
            if (child.get("parent_id") != registration.root_call_id
                    or child.get("trace_id") != root.get("trace_id") or "observation" not in child["output"]):
                raise TelemetryError("Public child trace hierarchy or observation mismatch.")
        snapshot = {"schema_version": "faultlab/v1", "source": "weave_verified",
                    "source_project": self.project, "metadata": registration.metadata,
                    "root_call_id": registration.root_call_id, "child_call_ids": list(registration.child_call_ids),
                    "calls": [records[key] for key in expected]}
        return {**snapshot, "digest": digest(snapshot), "retrieved_at": utc_now()}

    async def read(self, registration: TraceRegistration, *, stopped=lambda: False) -> EvidenceReadResult:
        try:
            self._authorized(registration)
        except TelemetryError:
            return EvidenceReadResult("weave_error", "REJECTED", error_code="NOT_AUTHORIZED")
        deadline = self.clock() + self.deadline_seconds
        try:
            if stopped():
                return EvidenceReadResult("weave_pending", "RETRYABLE_ERROR", error_code="STOPPED")
            # A single deadline includes flush, every page/network operation, and polling.
            await self.worker.request("flush", {}, timeout_seconds=max(0.001, deadline - self.clock()))
            while self.clock() < deadline and not stopped():
                self._authorized(registration)
                calls = await self.worker.request("get_calls", {"call_ids": [registration.root_call_id, *registration.child_call_ids]},
                                                  timeout_seconds=max(0.001, deadline - self.clock()))
                if self.clock() >= deadline:
                    break
                snapshot = self._normalize(registration, calls)
                if snapshot is not None:
                    self._authorized(registration)
                    return EvidenceReadResult("weave_verified", "INGESTED", snapshot=snapshot)
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                await self.sleep(min(self.poll_seconds, remaining))
            return EvidenceReadResult("weave_pending", "RETRYABLE_ERROR", error_code="STOPPED" if stopped() else "DEADLINE")
        except TimeoutError:
            return EvidenceReadResult("weave_pending", "RETRYABLE_ERROR", error_code="DEADLINE")
        except TelemetryError as error:
            if str(error) == "Sponsor telemetry operation failed." or "worker" in str(error).lower():
                return EvidenceReadResult("weave_pending", "RETRYABLE_ERROR", error_code="TRANSPORT")
            return EvidenceReadResult("weave_error", "REJECTED", error_code="INVALID_EVIDENCE")
        except Exception:
            return EvidenceReadResult("weave_pending", "RETRYABLE_ERROR", error_code="TRANSPORT")
