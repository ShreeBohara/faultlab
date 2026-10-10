"""Bounded local JSONL transport for an explicitly selected trusted Python agent."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import signal
import sys

from pydantic import TypeAdapter

from app.contracts.models import ActorAction, canonical_json, content_hash
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError
from app.local_agents.source import PROTOCOL, SourceSnapshot

REQUEST_MODEL = "openai/gpt-oss-120b"  # Existing request contract only, never a responding model.
MAX_REQUEST_BYTES = 262_144
MAX_RESPONSE_BYTES = 65_536
MAX_STDERR_BYTES = 65_536
ACTION = TypeAdapter(ActorAction)
WORKER = Path(__file__).with_name("worker.py").resolve()


class LocalAgentError(RuntimeProviderError):
    """A fixed, nonretryable classification; never contains child diagnostics."""
    def __init__(self, local_code):
        super().__init__("Local agent execution failed", code="INVALID_RESPONSE_SHAPE", error_class="RuntimeError")
        self.local_code = local_code


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result
    def reject(_):
        raise ValueError("Nonfinite number")
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    # JSON permits exponents large enough to overflow the Python float parser.
    json.dumps(result, allow_nan=False)
    return result


def _bridge_identity():
    directory = Path(__file__).parent
    files = {name: sha256((directory / name).read_bytes()).hexdigest()
             for name in ("source.py", "transport.py", "worker.py")}
    executable = Path(sys.executable).resolve()
    return {"protocol": PROTOCOL, "bridge_hash": content_hash(files), "files": files,
            "python_version": sys.version, "python_executable_hash": sha256(executable.read_bytes()).hexdigest(),
            "python_implementation": sys.implementation.name,
            "guard_policy": "faultlab-local-accident-guards/v1", "security_sandbox": False,
            "managed_provider_calls": 0, "child_external_activity": "unobserved",
            "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
            "max_stderr_bytes": MAX_STDERR_BYTES}


class LocalAgentProvider:
    def __init__(self, source_snapshot: SourceSnapshot, work_root, *, turn_timeout_seconds=10.0):
        if os.name != "posix":
            raise ValueError("This local agent transport requires macOS or Linux")
        if type(turn_timeout_seconds) not in (int, float) or not math.isfinite(turn_timeout_seconds) or not 0 < turn_timeout_seconds <= 20:
            raise ValueError("Local turn timeout must be in (0, 20] seconds")
        self.snapshot = source_snapshot
        self.work_root = Path(work_root).resolve()
        self.turn_timeout_seconds = float(turn_timeout_seconds)
        self.identity = {**source_snapshot.descriptor, **_bridge_identity(),
                         "turn_timeout_seconds": self.turn_timeout_seconds}
        self.records = {}
        self.calls = 0
        self._session = None

    @asynccontextmanager
    async def episode(self, episode_id):
        if self._session is not None or episode_id in self.records:
            raise ValueError("Local agent episodes must be sequential and uniquely identified")
        if not isinstance(episode_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", episode_id):
            raise ValueError("Invalid local episode identity")
        self.work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        working = self.work_root / episode_id
        working.mkdir(mode=0o700, exist_ok=False)
        record = {"schema_version": "faultlab-local-agent-execution/v1", "episode_id": episode_id,
                  "source_hash": self.snapshot.source_hash, "identity": dict(self.identity),
                  "protocol_status": "NOT_STARTED", "errors": [], "request_count": 0,
                  "process_id": None, "work_directory": episode_id, "exit_code": None,
                  "process_creation_complete": False,
                  "report_completed": False, "cleanup_complete": False, "stderr_bytes": 0,
                  "turn_timeout_seconds": self.turn_timeout_seconds,
                  "requests": []}
        self.records[episode_id] = record
        session = {"record": record, "cwd": working, "process": None, "spawn_task": None, "stderr_task": None,
                   "stderr_limit": asyncio.get_running_loop().create_future()}
        self._session = session
        try:
            yield self
        finally:
            # EpisodeRunner owns scoring/interrupt classification. Teardown retains
            # its own failure rather than replacing a saved result with an exception.
            if not record["report_completed"] and record["protocol_status"] != "FAILED":
                self._record_failure("LOCAL_AGENT_NO_REPORT", session)
            cleanup = asyncio.create_task(self._cleanup(session))
            try:
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        self._record_failure("LOCAL_AGENT_CANCELLED", session)
                cleanup.result()
            except Exception:
                self._record_failure("LOCAL_AGENT_CLEANUP_FAILED", session)
            finally:
                self._session = None

    def _record_failure(self, code, session=None):
        record = (session or self._session)["record"]
        record["protocol_status"] = "FAILED"
        if code not in record["errors"]:
            record["errors"].append(code)

    def _fail(self, code):
        self._record_failure(code)
        raise LocalAgentError(code)

    async def _stderr(self, session):
        digest = sha256()
        while True:
            data = await session["process"].stderr.read(4096)
            if not data:
                break
            digest.update(data)
            record = session["record"]
            record["stderr_bytes"] += len(data)
            if record["stderr_bytes"] > MAX_STDERR_BYTES and not session["stderr_limit"].done():
                session["stderr_limit"].set_result(True)
        session["record"]["stderr_sha256"] = digest.hexdigest()

    async def _start(self, session):
        try:
            self.snapshot.verify()
            if _bridge_identity()["bridge_hash"] != self.identity["bridge_hash"]:
                self._fail("LOCAL_AGENT_BRIDGE_CHANGED")
        except LocalAgentError:
            raise
        except Exception:
            self._fail("LOCAL_AGENT_SOURCE_CHANGED")
        # Store ownership before the first await. Repeated cancellation of _start
        # cannot lose the creation task; episode cleanup adopts its eventual child.
        session["spawn_task"] = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, "-I", "-S", "-B", "-u", str(WORKER),
            str(self.snapshot.path), self.snapshot.source_hash,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=session["cwd"], env={"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            close_fds=True, start_new_session=True, limit=MAX_RESPONSE_BYTES + 1))
        process = await asyncio.shield(session["spawn_task"])
        self._adopt_process(session, process)
        if session["record"]["protocol_status"] != "FAILED":
            session["record"]["protocol_status"] = "RUNNING"

    def _adopt_process(self, session, process):
        session["process"] = process
        session["record"].update(process_id=process.pid, process_creation_complete=True)
        if session["stderr_task"] is None:
            session["stderr_task"] = asyncio.create_task(self._stderr(session))

    async def _bounded(self, awaitable, timeout):
        operation = asyncio.ensure_future(awaitable)
        try:
            done, _ = await asyncio.wait({operation, self._session["stderr_limit"]},
                                         timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if self._session["stderr_limit"] in done:
                self._fail("LOCAL_AGENT_STDERR_LIMIT")
            if operation not in done:
                self._fail("LOCAL_AGENT_TIMEOUT")
            return operation.result()
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)

    async def _clean_report_exit(self, session, timeout):
        process = session["process"]
        process.stdin.close()

        async def finish():
            # Any output after the report frame violates the one-response protocol.
            extra = await process.stdout.read(1)
            if extra:
                self._fail("LOCAL_AGENT_EXTRA_OUTPUT")
            code = await process.wait()
            await session["stderr_task"]
            session["record"]["exit_code"] = code
            if code != 0:
                self._fail("LOCAL_AGENT_EXIT_FAILED")

        await self._bounded(finish(), timeout)
        session["record"].update(report_completed=True, protocol_status="COMPLETED", cleanup_complete=True)

    async def _cleanup(self, session):
        spawn = session["spawn_task"]
        if spawn is not None and session["process"] is None:
            try:
                # This cleanup task is shielded by episode(). Do not cancel the
                # OS creation handoff or claim cleanup while its child is unknown.
                process = await asyncio.shield(spawn)
                self._adopt_process(session, process)
            except (Exception, asyncio.CancelledError):
                self._record_failure("LOCAL_AGENT_START_FAILED", session)
                session["record"].update(process_creation_complete=spawn.done(), cleanup_complete=False)
                return
        process = session["process"]
        if process is None:
            session["record"].update(process_creation_complete=True, cleanup_complete=True)
            return
        async def drain_output():
            while await process.stdout.read(4096):
                pass
        stdout_drain = asyncio.create_task(drain_output())
        cleanup_ok = True
        readers = [stdout_drain]
        if session["stderr_task"] is not None:
            readers.append(session["stderr_task"])
        try:
            if process.stdin is not None:
                process.stdin.close()
            if not session["record"]["report_completed"]:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.25)
                except TimeoutError:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await asyncio.wait_for(process.wait(), timeout=1)
            await asyncio.wait_for(asyncio.gather(*readers), timeout=0.5)
        except Exception:
            self._record_failure("LOCAL_AGENT_CLEANUP_FAILED", session)
            cleanup_ok = False
        finally:
            # Even an exceptional wait/pipe path retains ownership of the child
            # and every reader. A failed cleanup can never leave a green record.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError:
                    cleanup_ok = False
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except Exception:
                    cleanup_ok = False
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            if not cleanup_ok or process.returncode is None:
                self._record_failure("LOCAL_AGENT_CLEANUP_FAILED", session)
            session["record"].update(exit_code=process.returncode,
                                     cleanup_complete=cleanup_ok and process.returncode is not None
                                     and (spawn is None or spawn.done()))

    async def complete(self, messages, *, role="actor", timeout_seconds=20, response_contract=None, **kwargs):
        session = self._session
        if session is None:
            raise LocalAgentError("LOCAL_AGENT_NO_SESSION")
        if session["record"]["protocol_status"] in ("FAILED", "COMPLETED"):
            self._fail("LOCAL_AGENT_SESSION_CLOSED")
        if role != "actor" or response_contract not in (None, "actor_final_report"):
            self._fail("LOCAL_AGENT_INVALID_REQUEST")
        if (not isinstance(messages, list) or not messages or any(
                not isinstance(message, dict) or set(message) != {"role", "content"}
                or message["role"] not in ("system", "user", "assistant")
                or not isinstance(message["content"], str) for message in messages)):
            self._fail("LOCAL_AGENT_INVALID_REQUEST")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            self._fail("LOCAL_AGENT_INVALID_REQUEST")
        # Leave a small margin for the Actor's outer episode deadline and cleanup.
        timeout = min(self.turn_timeout_seconds, max(0.001, float(timeout_seconds) - 0.05))
        started = asyncio.get_running_loop().time()
        request_record = None
        try:
            if session["process"] is None:
                await self._bounded(self._start(session), timeout)
            session["record"]["request_count"] += 1
            self.calls += 1
            request_id = f"{session['record']['episode_id']}:{session['record']['request_count']}"
            request = {"protocol": PROTOCOL, "request_id": request_id,
                       "messages": messages, "response_contract": response_contract}
            encoded = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
            if len(encoded) > MAX_REQUEST_BYTES:
                self._fail("LOCAL_AGENT_REQUEST_LIMIT")
            if session["record"]["request_count"] > 8:
                self._fail("LOCAL_AGENT_TURN_LIMIT")
            request_record = {"request_id": request_id, "request_sha256": sha256(encoded).hexdigest(),
                              "request_bytes": len(encoded), "timeout_seconds": timeout}
            session["record"]["requests"].append(request_record)
            process = session["process"]

            async def exchange():
                process.stdin.write(encoded)
                await process.stdin.drain()
                return await process.stdout.readline()

            remaining = max(0.001, timeout - (asyncio.get_running_loop().time() - started))
            raw = await self._bounded(exchange(), remaining)
            if not raw:
                self._fail("LOCAL_AGENT_EOF")
            if len(raw) > MAX_RESPONSE_BYTES or not raw.endswith(b"\n"):
                self._fail("LOCAL_AGENT_RESPONSE_LIMIT")
            response = _strict_json(raw.decode("utf-8", errors="strict"))
            if (not isinstance(response, dict) or set(response) != {"protocol", "request_id", "action"}
                    or response["protocol"] != PROTOCOL or response["request_id"] != request_id):
                self._fail("LOCAL_AGENT_INVALID_ENVELOPE")
            action = response["action"]
            content = canonical_json(action)
            ACTION.validate_json(content, strict=True)
            request_record.update(response_sha256=sha256(raw).hexdigest(), response_bytes=len(raw),
                                  action_sha256=sha256(content.encode("utf-8")).hexdigest(),
                                  validated_action=action, delivery_status="PENDING")
            if response_contract == "actor_final_report" and action.get("kind") != "report":
                self._fail("LOCAL_AGENT_REPORT_REQUIRED")
            if action.get("kind") == "report":
                remaining = max(0.001, timeout - (asyncio.get_running_loop().time() - started))
                await self._clean_report_exit(session, remaining)
            # Original values are retained; the validated model is not dumped back
            # to JSON, so omitted/default fields and citations are never rewritten.
            request_record["delivery_status"] = "RETURNED_TO_ACTOR"
            return RuntimeGeneration(content, REQUEST_MODEL, cost_usd=0.0)
        except asyncio.CancelledError:
            if request_record is not None and "validated_action" in request_record:
                request_record["delivery_status"] = "WITHHELD"
            self._record_failure("LOCAL_AGENT_CANCELLED", session)
            raise
        except LocalAgentError:
            if request_record is not None and "validated_action" in request_record:
                request_record["delivery_status"] = "WITHHELD"
            raise
        except Exception:
            if request_record is not None and "validated_action" in request_record:
                request_record["delivery_status"] = "WITHHELD"
            self._fail("LOCAL_AGENT_PROTOCOL_ERROR")
