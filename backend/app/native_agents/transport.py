"""Bounded child-initiated RPC for a reviewed, operator-selected native agent.

Only process lifetime helpers are inherited from the existing local transport.
Its decision callback protocol and its worker are never used or changed here.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import copy, deepcopy
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from pydantic import ValidationError

from app.agents.actor import ActorReportError
from app.contracts.models import TaskReport, canonical_json, content_hash
from app.integrations.external_agent import TASK_CONTRACT
from app.integrations.registry import verify_native_source
from app.local_agents.transport import LocalAgentProvider, _strict_json
from app.native_agents.actor import MODEL_ID, NativeBridge, NativeReportBlocked
from app.native_agents.source import PROTOCOL
from app.providers.runtime import RuntimeProviderError
from app.lab.budgets import BudgetExhausted, StopRequested

MAX_REQUEST_BYTES = 65_536       # Child -> parent, including native memory.
MAX_RESPONSE_BYTES = 262_144    # Parent -> child public observations/task only.
MAX_REQUESTS = 40
WORKER = Path(__file__).with_name("worker.py").resolve()
TOOLS = {
    "get_order": ({}, "string"),
    "update_order": ({"desired_shipping": {"type": "string", "description": "Must be express."}}, "string"),
    "get_operation_status": ({"service": {"type": "string", "description": "orders or notifications"}}, "string"),
    "send_confirmation": ({}, "string"),
    "final_answer": ({"answer": {"type": "object", "description": "Exact TaskReport object."}}, "object"),
}
CONFIGURATION = {"max_steps": 8, "planning_interval": None, "max_tool_threads": 1,
                 "stream_outputs": False, "reset": True, "return_full_result": False}


class NativeAgentError(RuntimeProviderError):
    def __init__(self, native_code):
        super().__init__("Native agent execution failed", code="INVALID_RESPONSE_SHAPE", error_class="RuntimeError")
        self.native_code = native_code


def _bridge_identity():
    from app.native_agents.model import identity as model_identity
    root = Path(__file__).parents[1]
    names = ("native_agents/source.py", "native_agents/transport.py", "native_agents/worker.py", "native_agents/actor.py",
             "local_agents/source.py", "local_agents/transport.py", "integrations/external_agent.py",
             "integrations/external_agent_v2.py", "agents/progress.py")
    files = {name: sha256((root / name).read_bytes()).hexdigest() for name in names}
    executable = Path(sys.executable).resolve()
    return {"protocol": PROTOCOL, "bridge_hash": content_hash(files), "files": files,
            "framework_version": "1.26.0", "framework_source_hash": verify_native_source(),
            "model_id": MODEL_ID, "model_identity": model_identity(),
            "python_version": sys.version, "python_executable_hash": sha256(executable.read_bytes()).hexdigest(),
            "python_implementation": sys.implementation.name, "guard_policy": "faultlab-native-accident-guards/v1",
            "security_sandbox": False, "managed_provider_calls": 0, "child_external_activity": "unobserved",
            "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
            "max_stderr_bytes": 65_536, "max_requests": MAX_REQUESTS}


def valid_execution(record, snapshot, expected_identity=None):
    """Fail closed on persisted native execution, not just a scorer outcome."""
    if not isinstance(record, dict):
        return False
    try:
        return _valid_execution(record, snapshot, expected_identity)
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def _valid_execution(record, snapshot, expected_identity):
    requests = record.get("requests")
    final = record.get("final_report")
    ready = record.get("ready")
    identity = record.get("identity")
    if (not isinstance(identity, dict) or not isinstance(ready, dict) or not isinstance(final, dict)
            or not isinstance(requests, list) or not all(isinstance(request, dict) for request in requests)):
        return False
    if len(requests) < 4:
        return False
    original = TaskReport.model_validate_json(canonical_json(final.get("original_report")))
    decoded = TaskReport.model_validate_json(canonical_json(final.get("decoded_report")))
    event = final.get("submission_event")
    if not isinstance(event, dict) or not isinstance(event.get("evidence_labels"), dict):
        return False
    if (any(not isinstance(evidence_id, str) or not isinstance(label, str)
            for evidence_id, label in event["evidence_labels"].items())
            or len(set(event["evidence_labels"].values())) != len(event["evidence_labels"])):
        return False
    labels = {label: evidence_id for evidence_id, label in event["evidence_labels"].items()}
    expected_report = {**final["original_report"], "evidence_ids": [labels.get(token, token) for token in original.evidence_ids]}
    if canonical_json(decoded.model_dump(mode="json")) != canonical_json(expected_report):
        return False
    final_call = requests[-2]
    if (final_call.get("kind") != "tool"
            or final_call.get("payload") != {"name": "final_answer", "arguments": {"answer": final["original_report"]}}
            or final_call.get("tool_result") != final["decoded_report"] or final_call.get("response_kind") != "result"):
        return False
    model_requests = [request for request in requests if request.get("kind") == "model"]
    if not model_requests or _strict_json(model_requests[-1].get("model_output")) != final_call["payload"]:
        return False
    for request in requests:
        kind, payload = request.get("kind"), request.get("payload")
        frame = {"protocol": PROTOCOL, "request_id": request.get("request_id"), "kind": kind, "payload": payload}
        encoded = canonical_json(frame).encode("utf-8") + b"\n"
        if request.get("request_sha256") != sha256(encoded).hexdigest() or request.get("request_bytes") != len(encoded):
            return False
        if kind == "ready":
            result = {"ready": True}
        elif kind == "model":
            result = {"content": request.get("model_output"), "model_id": MODEL_ID, "input_tokens": 0, "output_tokens": 0}
        elif kind == "tool":
            result = request.get("tool_result")
        elif kind == "finished":
            result = {"finished": True}
        else:
            return False
        response_kind = request.get("response_kind")
        if response_kind not in ("result", "error") or (kind != "tool" and response_kind != "result"):
            return False
        response = {"protocol": PROTOCOL, "request_id": request.get("request_id"), "kind": response_kind, "payload": result}
        encoded_response = canonical_json(response).encode("utf-8") + b"\n"
        if (request.get("response_sha256") != sha256(encoded_response).hexdigest()
                or request.get("response_bytes") != len(encoded_response)):
            return False
    return bool(
        record.get("schema_version") == "faultlab-native-agent-execution/v1"
        and record.get("source_hash") == snapshot.source_hash
        and identity.get("source_hash") == snapshot.source_hash
        and (expected_identity is None or canonical_json(identity) == canonical_json(expected_identity))
        and record.get("protocol_status") == "COMPLETED" and record.get("errors") == []
        and record.get("process_creation_complete") is True and record.get("cleanup_complete") is True
        and record.get("report_completed") is True and type(record.get("exit_code")) is int and record["exit_code"] == 0
        and type(record.get("process_id")) is int and record["process_id"] > 0
        and isinstance(ready, dict) and ready.get("source_hash") == snapshot.source_hash
        and ready.get("framework_source_hash") == identity.get("framework_source_hash")
        and ready.get("framework_version") == identity.get("framework_version") == "1.26.0"
        and ready.get("model_id") == identity.get("model_id") == MODEL_ID
        and canonical_json(ready.get("configuration")) == canonical_json(CONFIGURATION)
        and record.get("ready_hash") == content_hash(ready)
        and record.get("prompt_hash") == content_hash(ready.get("prompt"))
        and record.get("native_configuration_hash") == content_hash({"configuration": ready.get("configuration"), "tools": ready.get("tools")})
        and isinstance(requests, list) and type(record.get("request_count")) is int
        and record["request_count"] == len(requests) and 3 <= len(requests) <= MAX_REQUESTS
        and [request.get("request_id") for request in requests] == [f"rpc-{n + 1}" for n in range(len(requests))]
        and all(request.get("delivery_status") == "RETURNED_TO_CHILD" for request in requests)
        and requests[0].get("kind") == "ready" and requests[-1].get("kind") == "finished"
        and requests[0].get("payload") == ready
        and requests[-1].get("payload") == {"report": record.get("native_return")}
        and type(record.get("model_calls")) is int and 1 <= record["model_calls"] <= 8
        and record["model_calls"] == sum(request.get("kind") == "model" for request in requests)
        and type(record.get("double_calls")) is int and record["double_calls"] == record["model_calls"]
        and type(record.get("tool_calls")) is int and record["tool_calls"] == sum(request.get("kind") == "tool" for request in requests)
        and isinstance(final, dict) and final.get("delivery_status") == "RETURNED_TO_RUNNER"
        and final.get("decoded_report") == record.get("native_return")
        and event.get("report") == final.get("decoded_report")
        and event.get("adapter_entrypoint_id") == "smolagents-user-code-v1"
        and event.get("cited_evidence_tokens") == original.evidence_ids
        and event.get("decoded_evidence_ids") == decoded.evidence_ids
        # JSON objects have no chronological order. Persisted canonical JSON
        # sorts opaque evidence IDs; shown order lives in this explicit list.
        and event.get("labels_shown_to_agent") == [f"obs-{index + 1}" for index in range(len(labels))]
        and set(event["labels_shown_to_agent"]) == set(labels)
        and isinstance(final.get("original_report"), dict))


class NativeAgentProvider(LocalAgentProvider):
    """A process binding, not a remote model provider or an ActorAction provider."""
    def __init__(self, source_snapshot, work_root, *, turn_timeout_seconds=10.0):
        super().__init__(source_snapshot, work_root, turn_timeout_seconds=turn_timeout_seconds)
        self.identity = {**source_snapshot.descriptor, **_bridge_identity(),
                         "turn_timeout_seconds": self.turn_timeout_seconds}
        self._identity_hash = content_hash(self.identity)
        self.dependencies = Path(metadata.distribution("smolagents").locate_file("")).resolve()

    @asynccontextmanager
    async def episode(self, episode_id):
        async with super().episode(episode_id):
            record = self._session["record"]
            record.update(schema_version="faultlab-native-agent-execution/v1", model_calls=0, double_calls=0, tool_calls=0,
                          ready=None, ready_hash=None, native_return=None, final_report=None)
            record["identity"] = deepcopy(self.identity)
            try:
                yield self
            finally:
                if record.get("final_report") and record["protocol_status"] != "COMPLETED":
                    record["final_report"]["delivery_status"] = "WITHHELD"

    def _record_failure(self, code, session=None):
        super()._record_failure(code.replace("LOCAL_AGENT_", "NATIVE_AGENT_"), session)

    def _fail(self, code):
        code = code.replace("LOCAL_AGENT_", "NATIVE_AGENT_")
        self._record_failure(code)
        raise NativeAgentError(code)

    async def complete(self, *args, **kwargs):
        raise NativeAgentError("NATIVE_AGENT_NOT_A_MODEL_PROVIDER")

    async def _start(self, session):
        try:
            self.snapshot.verify()
            current = _bridge_identity()
            if content_hash(self.identity) != self._identity_hash or current != {
                    key: self.identity[key] for key in current}:
                self._fail("NATIVE_AGENT_IDENTITY_CHANGED")
        except NativeAgentError:
            raise
        except Exception:
            self._fail("NATIVE_AGENT_SOURCE_CHANGED")
        # Preserve the tested double-cancellation ownership rule: the task exists
        # on the session before any await; inherited cleanup adopts and reaps it.
        session["spawn_task"] = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, "-I", "-S", "-B", "-u", str(WORKER), str(self.snapshot.path), self.snapshot.source_hash,
            str(self.dependencies), self.identity["framework_source_hash"],
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=session["cwd"], env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "HF_HUB_OFFLINE": "1"},
            close_fds=True, start_new_session=True, limit=MAX_REQUEST_BYTES + 1))
        process = await asyncio.shield(session["spawn_task"])
        self._adopt_process(session, process)
        if session["record"]["protocol_status"] != "FAILED":
            session["record"]["protocol_status"] = "RUNNING"

    async def _send(self, value):
        encoded = canonical_json(value).encode("utf-8") + b"\n"
        if len(encoded) > MAX_RESPONSE_BYTES:
            self._fail("NATIVE_AGENT_PARENT_FRAME_LIMIT")
        process = self._session["process"]
        process.stdin.write(encoded)
        await self._bounded(process.stdin.drain(), self.turn_timeout_seconds)
        return {"response_sha256": sha256(encoded).hexdigest(), "response_bytes": len(encoded)}

    def _ready(self, value):
        if (not isinstance(value, dict) or set(value) != {"source_hash", "framework_source_hash", "framework_version",
                "model_id", "configuration", "prompt", "tools"}
                or value["source_hash"] != self.snapshot.source_hash
                or value["framework_source_hash"] != self.identity["framework_source_hash"]
                or value["framework_version"] != "1.26.0" or value["model_id"] != MODEL_ID
                or canonical_json(value["configuration"]) != canonical_json(CONFIGURATION)):
            self._fail("NATIVE_AGENT_INVALID_READY")
        prompt = value["prompt"]
        if (not isinstance(prompt, dict) or set(prompt) != {"templates", "instructions", "system_prompt"}
                or not isinstance(prompt["templates"], dict) or not isinstance(prompt["system_prompt"], str)
                or not (prompt["instructions"] is None or isinstance(prompt["instructions"], str))):
            self._fail("NATIVE_AGENT_INVALID_READY")
        tools = value["tools"]
        if (not isinstance(tools, list) or len(tools) != len(TOOLS)
                or any(not isinstance(tool, dict) or set(tool) != {"name", "description", "inputs", "output_type"}
                       or tool.get("name") not in TOOLS or not isinstance(tool.get("description"), str)
                       or len(tool["description"]) > 4096 for tool in tools)
                or len({tool["name"] for tool in tools}) != len(TOOLS)):
            self._fail("NATIVE_AGENT_INVALID_READY")
        for tool in tools:
            inputs, output_type = TOOLS[tool["name"]]
            if canonical_json(tool["inputs"]) != canonical_json(inputs) or tool["output_type"] != output_type:
                self._fail("NATIVE_AGENT_INVALID_READY")
        record = self._session["record"]
        record.update(ready=value, ready_hash=content_hash(value), prompt_hash=content_hash(prompt),
                      native_configuration_hash=content_hash({"configuration": value["configuration"], "tools": tools}))

    def _model_request(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {"messages", "tools"}
                or payload["tools"] != self._session["record"]["ready"]["tools"]
                or not isinstance(payload["messages"], list) or not payload["messages"]):
            self._fail("NATIVE_AGENT_INVALID_MODEL_REQUEST")
        messages = []
        for message in payload["messages"]:
            if (not isinstance(message, dict) or set(message) != {"role", "content", "tool_calls"}
                    or message["role"] not in ("system", "user", "assistant", "tool-call", "tool-response")
                    or not isinstance(message["tool_calls"], list)
                    or not isinstance(message["content"], (str, list, type(None)))):
                self._fail("NATIVE_AGENT_INVALID_MODEL_REQUEST")
            calls = []
            for call in message["tool_calls"]:
                if (not isinstance(call, dict) or set(call) != {"id", "name", "arguments"}
                        or not isinstance(call["id"], str) or call["name"] not in TOOLS
                        or not isinstance(call["arguments"], (dict, str))):
                    self._fail("NATIVE_AGENT_INVALID_MODEL_REQUEST")
                calls.append(SimpleNamespace(id=call["id"], function=SimpleNamespace(name=call["name"], arguments=call["arguments"])))
            messages.append(SimpleNamespace(role=message["role"], content=message["content"], tool_calls=calls))
        return messages, [SimpleNamespace(**tool) for tool in payload["tools"]]

    async def execute(self, intent, context):
        from app.native_agents.model import NativeOrdersDouble
        episode_id = context.provenance.episode_id
        bridge = None
        try:
            async with self.episode(episode_id):
                session = self._session
                record = session["record"]
                copied = copy(context)
                copied.provider = NativeOrdersDouble()
                bridge = NativeBridge(copied, record)
                await self._bounded(self._start(session), self.turn_timeout_seconds)
                await self._send({"protocol": PROTOCOL, "kind": "start",
                                  "task": canonical_json({"task": intent, "contract": TASK_CONTRACT})})
                while True:
                    context.broker.meter.check()
                    raw = await self._bounded(session["process"].stdout.readline(), self.turn_timeout_seconds)
                    if not raw:
                        self._fail("NATIVE_AGENT_EOF")
                    if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
                        self._fail("NATIVE_AGENT_FRAME_LIMIT")
                    frame = _strict_json(raw.decode("utf-8", errors="strict"))
                    sequence = record["request_count"] + 1
                    if (not isinstance(frame, dict) or set(frame) != {"protocol", "request_id", "kind", "payload"}
                            or frame["protocol"] != PROTOCOL or frame["request_id"] != f"rpc-{sequence}"
                            or frame["kind"] not in ("ready", "model", "tool", "finished")):
                        self._fail("NATIVE_AGENT_INVALID_ENVELOPE")
                    if sequence > MAX_REQUESTS:
                        self._fail("NATIVE_AGENT_REQUEST_LIMIT")
                    kind, payload = frame["kind"], frame["payload"]
                    request = {"request_id": frame["request_id"], "kind": kind, "payload": payload,
                               "request_sha256": sha256(raw).hexdigest(), "request_bytes": len(raw),
                               "delivery_status": "RECEIVED"}
                    record["request_count"] = sequence
                    record["requests"].append(request)
                    response_kind = "result"
                    if kind == "ready":
                        if sequence != 1:
                            self._fail("NATIVE_AGENT_UNEXPECTED_READY")
                        self._ready(payload)
                        result = {"ready": True}
                    elif record["ready"] is None:
                        self._fail("NATIVE_AGENT_NOT_READY")
                    elif kind == "finished":
                        if (not isinstance(payload, dict) or set(payload) != {"report"} or bridge.pending is None
                                or canonical_json(payload["report"]) != canonical_json(bridge.pending["decoded_report"])):
                            self._fail("NATIVE_AGENT_INVALID_FINAL_RETURN")
                        record["native_return"] = payload["report"]
                        result = {"finished": True}
                    elif bridge.pending is not None:
                        self._fail("NATIVE_AGENT_REQUEST_AFTER_FINAL")
                    elif kind == "model":
                        messages, tools = self._model_request(payload)
                        record["model_calls"] += 1
                        previous = copied.provider.calls
                        try:
                            generation = await bridge.generate(messages, tools)
                        finally:
                            completed = copied.provider.calls - previous
                            self.calls += completed
                            record["double_calls"] += completed
                        request["model_output"] = generation.content
                        result = {"content": generation.content, "model_id": generation.model_id,
                                  "input_tokens": generation.input_tokens or 0, "output_tokens": generation.output_tokens or 0}
                    else:
                        if (not isinstance(payload, dict) or set(payload) != {"name", "arguments"}
                                or payload["name"] not in TOOLS or not isinstance(payload["arguments"], dict)):
                            self._fail("NATIVE_AGENT_INVALID_TOOL_REQUEST")
                        if not record["model_calls"]:
                            self._fail("NATIVE_AGENT_TOOL_BEFORE_MODEL")
                        record["tool_calls"] += 1
                        try:
                            result = await bridge.dispatch(payload["name"], payload["arguments"])
                        except NativeReportBlocked as blocked:
                            result, response_kind = {"code": "REPORT_BLOCKED", "public": blocked.public_payload}, "error"
                        except (ValidationError, ActorReportError, ValueError):
                            # Native tool error recovery remains native. Do not
                            # expose raw exceptions, private IDs, or source text.
                            result, response_kind = {"code": "TOOL_REJECTED"}, "error"
                        request["tool_result"] = result
                    response = {"protocol": PROTOCOL, "request_id": frame["request_id"],
                                "kind": response_kind, "payload": result}
                    request.update(await self._send(response), delivery_status="RETURNED_TO_CHILD", response_kind=response_kind)
                    if kind == "finished":
                        await self._clean_report_exit(session, self.turn_timeout_seconds)
                        break
            # Teardown may turn a superficially completed worker into a failure.
            # Submission and EpisodeContext completion happen after that boundary.
            if (record["protocol_status"] != "COMPLETED" or not record["cleanup_complete"]
                    or record["exit_code"] != 0 or not record["process_creation_complete"]):
                raise NativeAgentError("NATIVE_AGENT_CLEANUP_FAILED")
            return bridge.submit()
        except asyncio.CancelledError:
            if episode_id in self.records:
                self._record_failure("NATIVE_AGENT_CANCELLED", {"record": self.records[episode_id]})
            raise
        except NativeAgentError:
            raise
        except (BudgetExhausted, StopRequested):
            if episode_id in self.records:
                self._record_failure("NATIVE_AGENT_BUDGET_OR_STOP", {"record": self.records[episode_id]})
            raise
        except RuntimeProviderError:
            if episode_id in self.records:
                self._record_failure("NATIVE_AGENT_MODEL_FAILED", {"record": self.records[episode_id]})
            raise
        except Exception:
            if episode_id in self.records:
                self._record_failure("NATIVE_AGENT_PROTOCOL_ERROR", {"record": self.records[episode_id]})
            raise NativeAgentError("NATIVE_AGENT_PROTOCOL_ERROR") from None
        finally:
            if bridge is not None:
                bridge.close()
                if bridge.pending is not None and bridge.pending["delivery_status"] != "RETURNED_TO_RUNNER":
                    bridge.pending["delivery_status"] = "WITHHELD"
