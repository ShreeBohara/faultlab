"""Sanitized async spans that preserve original return and exception behavior."""

from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import asyncio
import time
import uuid

from app.telemetry.safety import TelemetryError, capture_allowed, public_json, utc_now


OPERATIONS = {"run_episode", "get_order", "update_order", "get_operation_status", "send_confirmation",
              "select_experiment", "reproduce_counterexample", "reduce_counterexample", "run_intervention",
              "diagnose", "propose_policy", "challenge_policy", "export_regression", "promotion_decision"}
_parent_call = ContextVar("faultlab_trace_parent", default=None)


@dataclass
class TraceSpan:
    call_id: str
    captured: bool
    output: dict | None = None

    def set_output(self, output):
        # Serialization belongs to telemetry finalization; it must not replace
        # a successful prototype result with a telemetry serialization failure.
        self.output = output


class TraceRecorder:
    def __init__(self, worker, outbox, *, secrets=(), frozen: bool = False):
        self.worker, self.outbox, self.secrets, self.frozen = worker, outbox, secrets, frozen

    @asynccontextmanager
    async def span(self, name: str, metadata, inputs: dict, *, parent_id: str | None = None):
        if name not in OPERATIONS:
            raise TelemetryError("Unregistered trace operation.")
        metadata = public_json(metadata, secrets=self.secrets)
        allowed = capture_allowed(metadata, frozen=self.frozen)
        call_id = str(uuid.uuid4())
        span = TraceSpan(call_id=call_id, captured=False)
        # Protected/replay detail never reaches SDK, including initialization.
        if not allowed:
            yield span
            return
        required = {"campaign_id", "episode_id", "execution_epoch", "origin", "arm", "split", "model_id",
                    "policy_hash", "contract_hash", "scorer_hash", "source_mode", "experiment_purpose",
                    "trial_index", "agent_registration_id", "study_id", "evidence_context_id"}
        if not required <= metadata.keys():
            raise TelemetryError("Trace metadata is incomplete.")
        payload = {"call_id": call_id, "name": name, "metadata": metadata,
                   "inputs": public_json(inputs, secrets=self.secrets), "parent_id": parent_id or _parent_call.get(),
                   "started_at": utc_now(), "output": None}
        self.outbox.store.put_record("trace_calls", call_id, payload)
        try:
            remote = await self.worker.request("start_call", payload, timeout_seconds=2)
            if remote.get("id") != call_id:
                raise TelemetryError("Trace identity mismatch.")
            span.captured = True
        except Exception:
            pass
        token = _parent_call.set(call_id)
        try:
            yield span
        except BaseException as error:
            span.output = {"terminal_status": "INTERRUPTED" if type(error).__name__ == "CancelledError" else "LAB_ERROR",
                           "report": None, "error_category": "PROTOTYPE_EXCEPTION"}
            from app.providers.runtime import RuntimeProviderError
            if isinstance(error, RuntimeProviderError):
                span.output["provider_diagnostics"] = error.diagnostics
            raise
        finally:
            _parent_call.reset(token)
            try:
                payload["output"] = public_json(span.output or {"terminal_status": "COMPLETED", "report": None}, secrets=self.secrets)
            except TelemetryError:
                payload["output"] = {"terminal_status": "TELEMETRY_REJECTED", "report": None, "error_category": "UNSAFE_TRACE_OUTPUT"}
            payload["ended_at"] = utc_now()
            self.outbox.store.put_record("trace_calls", call_id, payload)
            self.outbox.enqueue("trace", call_id, payload)
            if span.captured:
                try:
                    await self.worker.request("finish_call", {"call_id": call_id, "output": payload["output"], "ended_at": payload["ended_at"]}, timeout_seconds=2)
                except Exception:
                    pass

    async def retry_episode_upload(self, episode_id: str, *, deadline_seconds: float = 60, stopped=lambda: False):
        """Synchronize only saved trace records, parent before children; never execute code."""
        records = [r for r in self.outbox.store.list_records("trace_calls")
                   if r["metadata"].get("episode_id") == episode_id and r.get("ended_at")]
        records.sort(key=lambda r: (r.get("parent_id") is not None, r["started_at"]))
        if not 0 < deadline_seconds <= 60:
            raise TelemetryError("Invalid synchronization deadline.")
        deadline = time.monotonic() + deadline_seconds
        async with asyncio.timeout(deadline_seconds):
            for record in records:
                if stopped():
                    raise TelemetryError("Telemetry synchronization stopped.")
                await self.worker.request("restore_call", record, timeout_seconds=max(0.001, deadline - time.monotonic()))
            await self.worker.request("flush", {}, timeout_seconds=max(0.001, deadline - time.monotonic()))
        return [r["call_id"] for r in records]

    def episode_calls(self, episode_id: str):
        return [r for r in self.outbox.store.list_records("trace_calls") if r["metadata"].get("episode_id") == episode_id]
