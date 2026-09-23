"""Sanitized async spans that preserve original return and exception behavior."""

from contextlib import asynccontextmanager, contextmanager
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
_episode_deadline = ContextVar("faultlab_episode_deadline", default=None)
TRACE_FINISH_TIMEOUT_SECONDS = 2.0


@contextmanager
def episode_deadline(deadline):
    """Expose the runner's timeout disposition without mistaking a user cancel for it."""
    task = asyncio.current_task()
    token = _episode_deadline.set((deadline, task, task.cancelling()))
    try:
        yield
    finally:
        _episode_deadline.reset(token)


def _deadline_cancelled(error):
    context = _episode_deadline.get()
    if not isinstance(error, asyncio.CancelledError) or context is None:
        return False
    deadline, task, cancelling = context
    # asyncio.timeout converts only its own cancellation to TimeoutError. An
    # additional external cancellation must remain an interruption in both logs.
    return deadline.expired() and task.cancelling() == cancelling + 1


def complete_episode_work():
    """Close a timely returned report's work deadline, never pending cancellation."""
    context = _episode_deadline.get()
    if context is None:
        return True
    deadline, task, cancelling = context
    if task.cancelling() != cancelling:
        raise asyncio.CancelledError()
    when = deadline.when()
    if deadline.expired() or (when is not None and asyncio.get_running_loop().time() >= when):
        return False
    deadline.reschedule(None)
    return True


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
            from app.agents.actor import ActorReportError
            from app.lab.budgets import BudgetExhausted, StopRequested
            # These are valid terminal actor attempts, not infrastructure errors.
            # The Referee still decides which correctness checks failed.
            if name == "run_episode" and isinstance(error, (ActorReportError, BudgetExhausted)):
                span.output.update(terminal_status="COMPLETED", error_category=(
                    "ACTOR_REPORT_MISSING" if isinstance(error, ActorReportError) else "EPISODE_BUDGET_EXHAUSTED"))
            elif name == "run_episode" and (isinstance(error, TimeoutError) or _deadline_cancelled(error)):
                span.output.update(terminal_status="COMPLETED", error_category="EPISODE_DEADLINE_EXHAUSTED")
            elif isinstance(error, StopRequested):
                span.output.update(terminal_status="INTERRUPTED", error_category="STOP_REQUESTED")
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
            try:
                if span.captured:
                    try:
                        async with asyncio.timeout(TRACE_FINISH_TIMEOUT_SECONDS):
                            await self.worker.request("finish_call", {"call_id": call_id, "output": payload["output"], "ended_at": payload["ended_at"]}, timeout_seconds=TRACE_FINISH_TIMEOUT_SECONDS)
                    except asyncio.CancelledError as error:
                        if name == 'run_episode' and not _deadline_cancelled(error):
                            payload['output'] = {**payload['output'], 'terminal_status': 'INTERRUPTED',
                                                 'error_category': 'EXTERNAL_CANCELLATION'}
                            self.outbox.store.put_record('trace_calls', call_id, payload)
                        raise
                    except Exception:
                        pass
            finally:
                # The durable local call exists before delivery. Queue its final
                # disposition even when an operator cancels an in-flight upload.
                self.outbox.enqueue("trace", call_id, payload)

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
