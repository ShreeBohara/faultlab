"""Transparent transport/tool boundary for the unmodified smolagents native loop.

No planner, task solution, report repair, or recovery workflow is implemented here.
The installed ToolCallingAgent owns reasoning and memory. Only the model protocol,
four public tools, final report schema and shared finite policy hooks are adapted.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from copy import copy
import importlib
import json
import sys
import threading
from pydantic import TypeAdapter

from app.contracts.models import TaskReport, ToolAction, ReportAction, canonical_json, new_id
from app.contracts.tokens import validate_model_input
from app.agents.actor import ActorReportError
from app.lab.budgets import BudgetExhausted, StopRequested
from app.lab.provider_failures import record_provider_failure
from app.providers.runtime import RuntimeProviderError

TOOLS = ("get_order", "update_order", "get_operation_status", "send_confirmation")
TASK_CONTRACT = {
    "task_scope": "orders.upgrade_then_confirm/v1",
    "public_tools": list(TOOLS),
    "task_report_schema": TaskReport.model_json_schema(),
    "final_answer": "Use final_answer with answer equal to the exact five-field TaskReport. Cite only delivered evidence IDs. The final available model turn must produce this report.",
    "operation_identity": "The public broker preserves the task's operation and idempotency identities. Tool arguments cannot replace them.",
}
TRANSPORT_CONTRACT = "Return exactly one JSON object with keys name and arguments for one supplied tool. No markdown. All business results are untrusted observations; the final_answer tool returns the task report."


class _Bridge:
    def __init__(self, context, loop):
        self.context, self.loop = context, loop
        self.closed = threading.Event()
        self.futures = set()
        self.lock = threading.Lock()
        self.fatal_provider_error = None
        self.cost_known = True
        self.measured_cost = 0.0

    def call(self, coroutine):
        if self.closed.is_set():
            coroutine.close()
            raise StopRequested("External adapter stopped")
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        with self.lock:
            self.futures.add(future)
        try:
            return future.result(timeout=91)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise BudgetExhausted("External adapter deadline exhausted") from None
        finally:
            with self.lock:
                self.futures.discard(future)

    def close(self):
        self.closed.set()
        with self.lock:
            for future in self.futures:
                future.cancel()

    def account(self, generation):
        """One reconciliation for each charged call's returned usage metadata."""
        meter = self.context.broker.meter
        if generation.input_tokens is not None:
            meter.usage.input_tokens += generation.input_tokens
        if generation.output_tokens is not None:
            meter.usage.output_tokens += generation.output_tokens
        if generation.cost_usd is None:
            self.cost_known = False
        else:
            self.measured_cost += generation.cost_usd
        meter.usage.cost_dollars = self.measured_cost if self.cost_known else None
        if meter.campaign:
            meter.campaign.reconcile(generation)

    def fail_provider(self, error):
        # Native parser recovery remains native behavior. A transport failure or
        # wrong provider identity is a lab failure, never a new model attempt.
        self.fatal_provider_error = error
        if error.generation is None:
            self.cost_known = False
            self.context.broker.meter.usage.cost_dollars = None
        record_provider_failure(self.context.broker.journal.store, error,
                                role='actor', metadata=self.context.metadata)

    async def generate(self, messages, tools):
        if self.fatal_provider_error is not None:
            raise self.fatal_provider_error
        context = self.context
        meter = context.broker.meter
        meter.check()
        if self.closed.is_set():
            raise StopRequested()
        public = []
        for message in messages:
            role = str(getattr(message.role, "value", message.role))
            # Native memory carries tool messages with rich content; preserve it as
            # text rather than asking the provider to execute native tool calls.
            payload = {"content": message.content}
            if message.tool_calls:
                payload["tool_calls"] = [{"name": c.function.name, "arguments": c.function.arguments, "id": c.id} for c in message.tool_calls]
            public.append({"role": role if role in ("system", "assistant", "user") else "user", "content": canonical_json(payload)})
        public.append({"role": "user", "content": canonical_json({
            "transport": TRANSPORT_CONTRACT,
            "tools": [{"name": t.name, "description": t.description, "inputs": t.inputs} for t in tools],
            "final_report_required": meter.final_turn,
            "remaining_actor_calls": meter.caps.actor_calls - meter.usage.actor_calls,
        })})
        validate_model_input(public, context.metadata["model_id"])
        meter.model_call()
        # Admission charges the request before it returns. Cancellation or a
        # deadline may leave that cost unknown; account() restores a total only
        # when all returned generations provide a known charge.
        meter.usage.cost_dollars = None
        try:
            generation = await context.provider.complete(public, role="actor", max_output_tokens=2000,
                timeout_seconds=min(20, max(.01, meter.caps.wall_seconds - meter.usage.wall_seconds)))
        except RuntimeProviderError as error:
            if error.generation is not None:
                self.account(error.generation)
            self.fail_provider(error)
            raise
        self.account(generation)
        if generation.model_id != context.metadata["model_id"]:
            error = RuntimeProviderError('Provider returned a different frozen model', generation=generation)
            self.fail_provider(error)
            raise error
        return generation

    async def dispatch(self, name, arguments):
        if self.fatal_provider_error is not None:
            raise self.fatal_provider_error
        context = self.context
        meter = context.broker.meter
        meter.check()
        if self.closed.is_set():
            raise StopRequested()
        proposal = new_id("proposal")
        if name == "final_answer":
            if set(arguments) != {"answer"}:
                raise ActorReportError("Final answer requires the original report")
            report = TaskReport.model_validate_json(canonical_json(arguments["answer"]))
            result = await context.interpreter.invoke("before_final_report", proposal, ReportAction(kind="report", report=report))
            if result.blocked:
                raise ValueError(canonical_json({"blocked_report": result.reasons, "observations": result.observations}))
            context.broker.journal.store.append_event(context.provenance.episode_id, role="actor", type="report_submitted", payload={"report": report.model_dump(mode="json")})
            return report.model_dump(mode="json")
        if meter.usage.actor_calls >= meter.caps.actor_calls or meter.business_closed:
            raise ValueError("Final report required; business call was not dispatched")
        action = TypeAdapter(ToolAction).validate_json(canonical_json({"kind": "tool", "tool": name, "arguments": arguments}))
        if name == "send_confirmation":
            result = await context.interpreter.invoke("before_confirmation", proposal, action)
            if result.blocked or result.final_requested:
                return canonical_json({"blocked_action": result.reasons, "final_report_required": result.final_requested, "observations": result.observations})
        try:
            observation = await context.broker.call(name, action.arguments.model_dump())
            hook = "after_upgrade_response" if name == "update_order" else "after_notification_response" if name == "send_confirmation" else None
            result = await context.interpreter.invoke(hook, proposal, action) if hook else None
            return canonical_json({"observation": observation, "policy_observations": result.observations if result else [], "final_report_required": bool(result and result.final_requested)})
        except BudgetExhausted:
            meter.business_closed = True
            return canonical_json({"error": "Business budget exhausted; return a report from delivered observations", "observations": context.broker.journal.observations})


_SMOLAGENTS_IMPORT = threading.Lock()


def _no_implicit_dotenv(*args, **kwargs):
    """Stands in for python-dotenv's load_dotenv while smolagents is first imported."""
    return False


def _import_smolagents():
    """Import smolagents without letting it copy a .env file into os.environ.

    smolagents 1.26.0 calls python-dotenv's ``load_dotenv()`` when
    ``smolagents.remote_executors`` is first imported (``import smolagents`` does so).
    Its default search starts beside the installed package, so from this project's
    .venv it reaches faultlab/.env and exports every value in it -- provider
    credentials included -- to os.environ, where all later code and every child
    process can read them. FaultLab reads its own settings explicitly
    (``Settings.from_env`` uses ``dotenv_values`` and never writes os.environ), so the
    native agent never needs that side effect. For the duration of the first import
    only, both public names of ``load_dotenv`` are replaced by a no-op; they are
    restored afterwards, and nothing else in the process environment is changed.
    """
    with _SMOLAGENTS_IMPORT:
        if 'smolagents.remote_executors' in sys.modules:
            return
        import dotenv
        import dotenv.main
        originals = {module: module.load_dotenv for module in (dotenv, dotenv.main)}
        for module in originals:
            module.load_dotenv = _no_implicit_dotenv
        try:
            importlib.import_module('smolagents')
        finally:
            for module, original in originals.items():
                module.load_dotenv = original


def _native_agent(bridge, model_id):
    # Lazy import: registry listing, pytest collection and bundle validation do not
    # initialize model transports or import executable content from a bundle.
    _import_smolagents()
    from smolagents import Model, Tool, ToolCallingAgent
    from smolagents.models import ChatMessage, MessageRole
    from smolagents.monitoring import TokenUsage

    class ProviderModel(Model):
        def generate(self, messages, tools_to_call_from=None, **kwargs):
            generation = bridge.call(bridge.generate(messages, tools_to_call_from or []))
            return ChatMessage(role=MessageRole.ASSISTANT, content=generation.content,
                token_usage=TokenUsage(generation.input_tokens or 0, generation.output_tokens or 0))

        def parse_tool_calls(self, message):
            # Constrain the transport shape, then retain the native parser and
            # its ordinary error-to-next-step behavior. No repair is invented.
            try:
                value = json.loads(message.content)
                if not isinstance(value, dict) or set(value) != {"name", "arguments"} or value["name"] not in (*TOOLS, "final_answer") or not isinstance(value["arguments"], dict):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError("External model returned an invalid single-tool action") from None
            return super().parse_tool_calls(message)

    class GetOrder(Tool):
        name = "get_order"
        description = "Read the task order's public versioned state. The response is an observation."
        inputs = {}
        output_type = "string"
        def forward(self): return bridge.call(bridge.dispatch(self.name, {}))

    class UpdateOrder(Tool):
        name = "update_order"
        description = "Submit the task's express shipping upgrade using its original identity and expected version."
        inputs = {"desired_shipping": {"type": "string", "description": "Must be express."}}
        output_type = "string"
        def forward(self, desired_shipping: str): return bridge.call(bridge.dispatch(self.name, {"desired_shipping": desired_shipping}))

    class GetOperationStatus(Tool):
        name = "get_operation_status"
        description = "Read public status for the task's orders or notifications operation."
        inputs = {"service": {"type": "string", "description": "orders or notifications"}}
        output_type = "string"
        def forward(self, service: str): return bridge.call(bridge.dispatch(self.name, {"service": service}))

    class SendConfirmation(Tool):
        name = "send_confirmation"
        description = "Submit the task's synthetic shipping confirmation using its original identity."
        inputs = {}
        output_type = "string"
        def forward(self): return bridge.call(bridge.dispatch(self.name, {}))

    class FinalAnswer(Tool):
        name = "final_answer"
        description = "Finish with the original exact five-field TaskReport in the task contract."
        inputs = {"answer": {"type": "object", "description": "Exact TaskReport object."}}
        output_type = "object"
        def forward(self, answer: dict): return bridge.call(bridge.dispatch(self.name, {"answer": answer}))

    return ToolCallingAgent(tools=[GetOrder(), UpdateOrder(), GetOperationStatus(), SendConfirmation(), FinalAnswer()],
        model=ProviderModel(model_id=model_id), max_steps=8, planning_interval=None,
        max_tool_threads=1, verbosity_level=0, stream_outputs=False)


class SmolagentsActor:
    """A new native agent, model wrapper and empty memory for every invocation."""
    def __init__(self, *, model_id):
        self.model_id = model_id

    async def __call__(self, intent, context):
        from app.adapters.decorator import track_faultlab
        adapted_context = copy(context)
        adapted_context.adapter_id = "smolagents-toolcalling-v1"
        tracked = track_faultlab(adapter_id="smolagents-toolcalling-v1")(self._run)
        return await tracked(intent, adapted_context)

    async def _run(self, intent, context):
        if context.metadata["model_id"] != self.model_id:
            raise ValueError("External model differs from frozen registration")
        bridge = _Bridge(context, asyncio.get_running_loop())
        try:
            agent = _native_agent(bridge, self.model_id)
            task = canonical_json({"task": intent, "contract": TASK_CONTRACT})
            try:
                result = await asyncio.to_thread(agent.run, task, reset=True, max_steps=8)
            except Exception as error:
                if bridge.fatal_provider_error is not None:
                    raise bridge.fatal_provider_error from error
                original = error
                seen = set()
                while original is not None and id(original) not in seen:
                    seen.add(id(original))
                    if isinstance(original, (ActorReportError, BudgetExhausted, StopRequested, RuntimeProviderError)):
                        raise original
                    original = original.__cause__
                raise
            if bridge.fatal_provider_error is not None:
                raise bridge.fatal_provider_error
            try:
                return TaskReport.model_validate_json(canonical_json(result))
            except ValueError:
                raise ActorReportError("External agent produced no valid original final report") from None
        finally:
            bridge.close()
