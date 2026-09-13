"""A killable SDK boundary; environment/logging changes stay in its child process.

The protocol has no model or business operation command. Retrying telemetry can
therefore never repeat an actor action. All requests originate in trusted backend
adapters after capture/authorization checks, never directly from HTTP or a model.
"""

import asyncio
from datetime import datetime
import multiprocessing
from typing import Any

from app.config import Settings
from app.telemetry.safety import TelemetryError, public_json


CALL_COLUMNS = ["id", "project_id", "parent_id", "trace_id", "op_name", "attributes", "inputs", "output", "ended_at", "exception"]


def _serial_call(call) -> dict:
    result = {}
    for name in CALL_COLUMNS:
        value = getattr(call, name, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        # Weave trace object proxies expose to_dict; only projected values cross.
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        result[name] = value
    # SDK WeaveDict/WeaveList retain a server/client reference as Python
    # attributes. Strip wrappers before IPC so neither credentials nor an
    # unpicklable transport lock can cross the process boundary.
    return public_json(result)


class SDKHandler:
    """SDK calls separated for offline signature/lifecycle testing with doubles."""
    def __init__(self, settings, weave, client, wandb=None):
        self.settings, self.weave, self.client, self.wandb = settings, weave, client, wandb
        self.calls, self.evaluations, self.predictions = {}, {}, {}

    def handle(self, command: str, payload: dict):
        if command == "restore_call":
            # Saved telemetry delivery is independent of prototype execution.
            # Reuse the exact remote identity before considering another write.
            call_id = payload["call_id"]
            try:
                existing = self.client.get_call(call_id, columns=CALL_COLUMNS)
            except ValueError as error:
                if str(error) != f"Call not found: {call_id}":
                    raise TelemetryError("Saved call lookup failed.") from None
                existing = None
            if existing is not None:
                saved = _serial_call(existing)
                attributes = saved.get("attributes") or {}
                expected_parent = payload.get("parent_id")
                parent = self.calls.get(expected_parent)
                expected_trace = parent.trace_id if parent is not None else call_id
                if (saved["id"] != call_id or saved["project_id"] != self.settings.project_path
                        or saved["parent_id"] != expected_parent or saved["trace_id"] != expected_trace
                        or (expected_parent is not None and parent is None)
                        or not isinstance(saved.get("op_name"), str)
                        or not saved["op_name"].startswith(f"weave:///{self.settings.project_path}/op/{payload['name']}:")
                        or any(attributes.get(k) != v for k, v in payload["metadata"].items())
                        or saved["inputs"] != payload["inputs"] or saved.get("exception")):
                    raise TelemetryError("Saved call identity conflicts with remote evidence.")
                if saved.get("ended_at") is not None:
                    if (saved["output"] != payload["output"]
                            or datetime.fromisoformat(saved["ended_at"]) != datetime.fromisoformat(payload["ended_at"])):
                        raise TelemetryError("Saved call completion conflicts with remote evidence.")
                    self.calls[call_id] = existing
                    return {"id": call_id, "reused": True}
                if saved["output"] is not None:
                    raise TelemetryError("Saved call has an inconsistent remote completion.")
                self.calls[call_id] = existing
            else:
                if payload.get("parent_id") is not None and payload["parent_id"] not in self.calls:
                    raise TelemetryError("Saved parent call is unavailable.")
                self.handle("start_call", payload)
            self.handle("finish_call", {"call_id": call_id, "output": payload["output"], "ended_at": payload["ended_at"]})
            return {"id": call_id, "reused": False}
        if command == "start_call":
            with self.weave.attributes(payload["metadata"]):
                call = self.client.create_call(payload["name"], inputs=payload["inputs"],
                    parent=self.calls.get(payload.get("parent_id")), attributes=payload["metadata"], use_stack=False,
                    _call_id_override=payload.get("call_id"),
                    started_at=datetime.fromisoformat(payload["started_at"]) if payload.get("started_at") else None)
            self.calls[call.id] = call
            return {"id": call.id, "url": call.ui_url}
        if command == "finish_call":
            self.client.finish_call(self.calls[payload["call_id"]], output=payload["output"],
                ended_at=datetime.fromisoformat(payload["ended_at"]) if payload.get("ended_at") else None)
            return {}
        if command == "flush":
            self.client.flush()
            return {}
        if command == "get_calls":
            ids = payload["call_ids"]
            if not ids or len(ids) > 19 or len(set(ids)) != len(ids):
                raise TelemetryError("Invalid bounded call inventory.")
            # The inventory is already an exact allowlist. Read each ID directly:
            # bulk pages may contain repeated IDs after telemetry delivery retries,
            # consuming their row limit before all requested children are returned.
            # The parent worker deadline still bounds the entire inventory read.
            records = []
            for call_id in ids:
                try:
                    call = self.client.get_call(call_id, columns=CALL_COLUMNS)
                except ValueError:
                    # The pinned SDK raises ValueError when the exact ID is not
                    # visible yet. Leave it absent so the reader remains pending.
                    continue
                records.append(_serial_call(call))
            return records
        if command == "evaluation_init":
            key = payload["batch_id"]
            if key not in self.evaluations:
                self.evaluations[key] = self.weave.EvaluationLogger(name=payload["name"], model=payload["model_id"],
                    eval_attributes=payload["metadata"])
            return {}
        if command == "prediction":
            logger = self.evaluations[payload["batch_id"]]
            prediction = logger.log_prediction(inputs=payload["inputs"], output=payload["report"])
            for name, score in payload["scores"].items():
                prediction.log_score(scorer=name, score=score)
            prediction.finish()
            call = prediction.predict_and_score_call
            self.predictions.setdefault(payload["batch_id"], {})[call.id] = payload
            return {"id": call.id, "url": call.ui_url}
        if command == "evaluation_summary":
            logger = self.evaluations[payload["batch_id"]]
            logger.log_summary(payload["summary"], auto_summarize=False)
            self.client.flush()
            call = logger._evaluate_call  # Pinned 0.53.9; public ui_url alone has no call ID accessor.
            saved = self.client.get_call(call.id, columns=CALL_COLUMNS)
            if saved.id != call.id or saved.project_id != self.settings.project_path or saved.ended_at is None:
                raise TelemetryError("Evaluation readback is incomplete.")
            # Weave 0.53.9 preserves explicit summaries both at the top level
            # and under `output`, even with auto_summarize=False.
            expected_summary = {**payload["summary"], "output": payload["summary"]}
            if public_json(getattr(saved, "output", None)) != expected_summary:
                raise TelemetryError("Evaluation summary differs from the persisted fixed summary.")
            for prediction_id, row in self.predictions.get(payload["batch_id"], {}).items():
                prediction = self.client.get_call(prediction_id, columns=CALL_COLUMNS)
                output = public_json(getattr(prediction, "output", None))
                if (prediction.id != prediction_id or prediction.project_id != self.settings.project_path or prediction.ended_at is None
                        or not isinstance(output, dict) or output.get("output") != row["report"] or output.get("scores") != row["scores"]):
                    raise TelemetryError("Prediction/score readback differs from persisted evidence.")
            return {"id": call.id, "url": call.ui_url, "verified": True}
        if command == "dataset":
            ref = self.weave.publish(self.weave.Dataset(name=payload["name"], rows=payload["rows"]))
            uri = ref.uri()
            self.client.flush()
            # Object read-back, rather than publish completion alone, establishes persistence.
            saved = self.weave.ref(uri).get()
            if saved is None or public_json(list(saved.rows)) != payload["rows"]:
                raise TelemetryError("Dataset readback is incomplete.")
            return {"ref": uri, "verified": True}
        if command == "campaign_bridge":
            if self.wandb is None:
                import wandb
                self.wandb = wandb
            run = self.wandb.init(entity=self.settings.wandb_entity, project=self.settings.wandb_project,
                id=payload["run_id"], name=payload["name"], resume="allow", job_type="faultlab-development-summary",
                settings=self.wandb.Settings(api_key=self.settings.wandb_api_key, silent=True, console="off", disable_git=True))
            try:
                run.summary.update(payload["summary"])
                result = {"run_id": run.id, "url": run.url}
                run.finish(exit_code=0)
                return result
            except Exception:
                run.finish(exit_code=1)
                raise
        raise TelemetryError("Unknown telemetry operation.")


def _worker_main(pipe, settings: Settings):
    from app.providers.weave_tracing import WEAVE_SETTINGS, _weave_environment, quiet_sdk_output
    # Initialized once for this private worker lifetime, never around backend requests.
    with quiet_sdk_output(), _weave_environment(settings):
        handler = None
        try:
            while True:
                command, payload = pipe.recv()
                if command == "shutdown":
                    break
                try:
                    if command == "initialize":
                        import weave
                        client = weave.init(settings.project_path, settings=WEAVE_SETTINGS)
                        handler = SDKHandler(settings, weave, client)
                        result = {}
                    elif handler is None:
                        raise TelemetryError("Telemetry worker is not initialized.")
                    else:
                        result = handler.handle(command, payload)
                    pipe.send({"ok": True, "value": result})
                except Exception:
                    # Do not send SDK exception text, credentials or objects over IPC.
                    pipe.send({"ok": False, "error": "Sponsor telemetry operation failed."})
        except (EOFError, BrokenPipeError):
            pass
        finally:
            pipe.close()


class WeaveWorker:
    def __init__(self, settings: Settings, *, live_authorized: bool = False):
        self._settings, self._authorized = settings, live_authorized
        self._process = self._pipe = None
        self._lock = asyncio.Lock()

    async def start(self, *, timeout_seconds: float = 20):
        if not self._authorized:
            raise TelemetryError("An explicit bounded live action is required.")
        self._settings.require_wandb()
        if self._process is not None:
            return
        ctx = multiprocessing.get_context("spawn")
        self._pipe, child = ctx.Pipe()
        self._process = ctx.Process(target=_worker_main, args=(child, self._settings), daemon=True)
        self._process.start()
        child.close()
        await self.request("initialize", {}, timeout_seconds=timeout_seconds)

    async def request(self, command: str, payload: dict, *, timeout_seconds: float = 20) -> Any:
        if not 0 < timeout_seconds <= 60:
            raise TelemetryError("Invalid telemetry deadline.")
        if self._process is None or not self._process.is_alive():
            raise TelemetryError("Telemetry worker is unavailable.")
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._lock:
                    self._pipe.send((command, payload))
                    # poll is bounded even if the SDK blocks; timeout kills the worker.
                    available = await asyncio.to_thread(self._pipe.poll, timeout_seconds)
                    if not available:
                        raise TimeoutError()
                    result = self._pipe.recv()
                    if not result["ok"]:
                        raise TelemetryError(result["error"])
                    return result["value"]
        except (asyncio.CancelledError, TimeoutError):
            self.abort()
            raise
        except (EOFError, OSError):
            self.abort()
            raise TelemetryError("Telemetry worker was interrupted.") from None

    def abort(self):
        if self._process is not None:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=0.1)
            if self._process.is_alive():
                self._process.kill()
            self._process = None
        if self._pipe is not None:
            self._pipe.close()
            self._pipe = None

    async def close(self):
        self.abort()
