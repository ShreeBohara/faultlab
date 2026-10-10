"""Dependency worker for an explicitly trusted native constructor.

The audit hook is an accident guard, not a security sandbox. The interpreter
starts without site initialization; only the operator's installed dependency
directory is added, without executing .pth files or loading a project .env.
"""
from __future__ import annotations

import contextlib
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import sysconfig

PROTOCOL = "faultlab-native-agent/v1"
MODEL_ID = "faultlab-native-orders-double/v1"
REVISION = "12c1bc820eca50ace6f80a21d90426d41d74f845"
MAX_PARENT_BYTES = 262_144
MAX_CHILD_BYTES = 65_536


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result
    def reject(_):
        raise ValueError("Nonfinite number")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    canonical(value)
    return value


def guards(source, worker, working, dependencies):
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    dynamic = Path(sysconfig.get_config_var("DESTSHARED") or stdlib / "lib-dynload").resolve()
    state = {"bootstrap": True}

    def require_path(value, writing=False):
        if isinstance(value, int):
            if value in (0, 1, 2):
                return
            raise PermissionError("Native accident guard refused descriptor access")
        path = Path(os.fsdecode(value)).resolve()
        if any(part == ".env" or part.startswith(".env.") for part in path.parts):
            raise PermissionError("Native accident guard refused credential file access")
        allowed = path.is_relative_to(working) if writing else (
            path in (source, worker) or any(path.is_relative_to(root) for root in (stdlib, dynamic, working, dependencies)))
        if not allowed:
            raise PermissionError("Native accident guard refused filesystem access")

    def audit(event, args):
        if (event.startswith(("socket.", "subprocess."))
                or (event.startswith("ctypes.") and not state["bootstrap"])
                or event in {"os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec", "os.spawn",
                             "os.kill", "os.killpg", "os.chroot", "os.setuid", "os.setgid"}):
            raise PermissionError("Native accident guard refused process or network access")
        if event == "open":
            name, mode, flags = args
            writing = any(char in (mode or "") for char in "wax+") or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            require_path(name, writing)
        elif event in {"os.listdir", "os.scandir"}:
            require_path(args[0] if args[0] is not None else working)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime"}:
            require_path(args[0], True)
        elif event in {"os.rename", "os.link"}:
            require_path(args[0], True)
            require_path(args[1], True)
        elif event in {"os.symlink", "os.chdir", "os.fchdir"}:
            raise PermissionError("Native accident guard refused filesystem alias change")
    sys.addaudithook(audit)
    return state


def framework_hash(directory):
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Native source symlink")
        if path.is_file() and path.suffix in (".py", ".yaml", ".yml"):
            files[path.relative_to(directory).as_posix()] = sha256(path.read_bytes()).hexdigest()
    return sha256(canonical({"revision": REVISION, "files": files}).encode()).hexdigest()


def main():
    if len(sys.argv) != 5:
        return 64
    source, expected_source, dependencies, expected_framework = (
        Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3]).resolve(), sys.argv[4])
    raw = source.read_bytes()
    if not raw or len(raw) > 262_144 or sha256(raw).hexdigest() != expected_source:
        return 65
    sys.dont_write_bytecode = True
    state = guards(source, Path(__file__).resolve(), Path.cwd().resolve(), dependencies)
    # No site.main(), arbitrary sys.path inherited from the parent, or .pth execution.
    sys.path.append(str(dependencies))
    output, input_stream = sys.stdout.buffer, sys.stdin.buffer

    def unraisable(_):
        os._exit(71)
    sys.unraisablehook = unraisable

    with contextlib.redirect_stdout(sys.stderr):
        # smolagents imports remote_executors, which calls load_dotenv at import.
        # Disable that implicit behavior before the import, even under -I -S.
        import dotenv
        import dotenv.main
        dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *a, **kw: False
        from smolagents import Model, Tool, ToolCallingAgent, __version__
        from smolagents.models import ChatMessage, MessageRole
        from smolagents.monitoring import TokenUsage
    state["bootstrap"] = False
    actual_framework = framework_hash(dependencies / "smolagents")
    if __version__ != "1.26.0" or actual_framework != expected_framework:
        return 66

    first = input_stream.readline(MAX_PARENT_BYTES + 1)
    if len(first) > MAX_PARENT_BYTES or not first.endswith(b"\n"):
        return 67
    start = strict_json(first.decode("utf-8"))
    if (not isinstance(start, dict) or set(start) != {"protocol", "kind", "task"}
            or start["protocol"] != PROTOCOL or start["kind"] != "start" or not isinstance(start["task"], str)):
        return 68
    sequence, active, constructor_called_capability = 0, False, False

    def rpc(kind, payload):
        nonlocal sequence, constructor_called_capability
        if kind in ("model", "tool") and not active:
            constructor_called_capability = True
            raise PermissionError("Constructor cannot call model or tools")
        sequence += 1
        request_id = f"rpc-{sequence}"
        frame = {"protocol": PROTOCOL, "request_id": request_id, "kind": kind, "payload": payload}
        encoded = canonical(frame).encode("utf-8") + b"\n"
        if len(encoded) > MAX_CHILD_BYTES:
            raise ValueError("Child frame too large")
        output.write(encoded)
        output.flush()
        response = input_stream.readline(MAX_PARENT_BYTES + 1)
        if len(response) > MAX_PARENT_BYTES or not response.endswith(b"\n"):
            raise ValueError("Missing or oversized response")
        value = strict_json(response.decode("utf-8"))
        if (not isinstance(value, dict) or set(value) != {"protocol", "request_id", "kind", "payload"}
                or value["protocol"] != PROTOCOL or value["request_id"] != request_id
                or value["kind"] not in ("result", "error")):
            raise ValueError("Invalid parent response")
        if value["kind"] == "error":
            # Parent error payloads contain fixed codes and, for a policy block,
            # only public observations deliberately delivered to the native loop.
            raise ValueError(canonical(value["payload"]))
        return value["payload"]

    def tool_metadata(tool):
        return {"name": tool.name, "description": tool.description, "inputs": tool.inputs, "output_type": tool.output_type}

    def message_dict(message):
        role = getattr(message, "role", None)
        return {"role": str(getattr(role, "value", role)), "content": message.content,
                "tool_calls": [{"id": call.id, "name": call.function.name, "arguments": call.function.arguments}
                               for call in (message.tool_calls or [])]}

    class ParentModel(Model):
        def generate(self, messages, tools_to_call_from=None, **kwargs):
            result = rpc("model", {"messages": [message_dict(message) for message in messages],
                                   "tools": [tool_metadata(tool) for tool in (tools_to_call_from or [])]})
            if (not isinstance(result, dict) or set(result) != {"content", "model_id", "input_tokens", "output_tokens"}
                    or result["model_id"] != MODEL_ID or not isinstance(result["content"], str)):
                raise ValueError("Invalid model result")
            return ChatMessage(role=MessageRole.ASSISTANT, content=result["content"],
                               token_usage=TokenUsage(result["input_tokens"], result["output_tokens"]))

        def parse_tool_calls(self, message):
            value = strict_json(message.content)
            if (not isinstance(value, dict) or set(value) != {"name", "arguments"}
                    or value["name"] not in tools_by_name or not isinstance(value["arguments"], dict)):
                raise ValueError("Invalid single-tool model action")
            return super().parse_tool_calls(message)

    class GetOrder(Tool):
        name = "get_order"
        description = "Read the task order's public versioned state. The response is an observation."
        inputs = {}
        output_type = "string"
        def forward(self): return rpc("tool", {"name": self.name, "arguments": {}})

    class UpdateOrder(Tool):
        name = "update_order"
        description = "Submit the task's express shipping upgrade using its original identity and expected version."
        inputs = {"desired_shipping": {"type": "string", "description": "Must be express."}}
        output_type = "string"
        def forward(self, desired_shipping: str):
            return rpc("tool", {"name": self.name, "arguments": {"desired_shipping": desired_shipping}})

    class GetOperationStatus(Tool):
        name = "get_operation_status"
        description = "Read public status for the task's orders or notifications operation."
        inputs = {"service": {"type": "string", "description": "orders or notifications"}}
        output_type = "string"
        def forward(self, service: str): return rpc("tool", {"name": self.name, "arguments": {"service": service}})

    class SendConfirmation(Tool):
        name = "send_confirmation"
        description = "Submit the task's synthetic shipping confirmation using its original identity."
        inputs = {}
        output_type = "string"
        def forward(self): return rpc("tool", {"name": self.name, "arguments": {}})

    class FinalAnswer(Tool):
        name = "final_answer"
        description = "Finish with the original exact five-field TaskReport in the task contract."
        inputs = {"answer": {"type": "object", "description": "Exact TaskReport object."}}
        output_type = "object"
        def forward(self, answer: dict): return rpc("tool", {"name": self.name, "arguments": {"answer": answer}})

    with contextlib.redirect_stdout(sys.stderr):
        model = ParentModel(model_id=MODEL_ID)
        tools = [GetOrder(), UpdateOrder(), GetOperationStatus(), SendConfirmation(), FinalAnswer()]
        model_methods = {name: getattr(ParentModel, name) for name in ("generate", "parse_tool_calls")}
        final_forward = FinalAnswer.forward
        tools_by_name = {tool.name: tool for tool in tools}
        expected_tools = {tool.name: tool_metadata(tool) for tool in tools}
        # Capture native methods before importing user code. Exact native type plus
        # unchanged methods prevents accidentally replacing the framework loop.
        methods = {name: getattr(ToolCallingAgent, name) for name in
                   ("run", "_run_stream", "_step_stream", "process_tool_calls", "execute_tool_call", "write_memory_to_messages")}
        namespace = {"__name__": "faultlab_native_user_agent", "__file__": str(source)}
        exec(compile(raw, str(source), "exec"), namespace)
        constructor = namespace.get("build_agent")
        if not callable(constructor):
            return 69
        agent = constructor(model, tools)
        if (constructor_called_capability or type(agent) is not ToolCallingAgent or agent.model is not model
                or agent.max_steps != 8 or type(agent.max_steps) is not int
                or agent.planning_interval is not None or agent.max_tool_threads != 1
                or agent.stream_outputs is not False or agent.managed_agents
                or agent.tools.get("final_answer") is not tools_by_name["final_answer"]
                or set(agent.tools) != set(tools_by_name)):
            return 69
        if (any(getattr(ParentModel, name) is not method or name in model.__dict__ for name, method in model_methods.items())
                or FinalAnswer.forward is not final_forward or "forward" in tools_by_name["final_answer"].__dict__):
            return 69
        for name, original in methods.items():
            if getattr(ToolCallingAgent, name) is not original or name in agent.__dict__:
                return 69
        for name, tool in agent.tools.items():
            row = tool_metadata(tool)
            if (row["name"] != name or row["inputs"] != expected_tools[name]["inputs"]
                    or row["output_type"] != expected_tools[name]["output_type"]
                    or not isinstance(row["description"], str)):
                return 69
        prompt = {"templates": agent.prompt_templates, "instructions": agent.instructions,
                  "system_prompt": agent.system_prompt}
        ready = {"source_hash": expected_source, "framework_source_hash": actual_framework,
                 "framework_version": __version__, "model_id": MODEL_ID,
                 "configuration": {"max_steps": 8, "planning_interval": None, "max_tool_threads": 1,
                                   "stream_outputs": False, "reset": True, "return_full_result": False},
                 "prompt": prompt, "tools": [tool_metadata(tool) for tool in agent.tools.values()]}
        rpc("ready", ready)
        active = True
        result = agent.run(start["task"], reset=True, max_steps=8, return_full_result=False)
        active = False
        rpc("finished", {"report": result})
    # Require parent EOF after the final acknowledgement. Any later authored
    # output/crash is caught before the parent accepts the original final result.
    if input_stream.read(1):
        return 68
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        code = 70
    raise SystemExit(code)
