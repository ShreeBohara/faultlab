"""Bounded, explicitly initialized Weave tracing for the standalone check CLI."""

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any

from app.config import Settings
from app.providers import ProviderCheckError

WEAVE_SETTINGS: dict[str, Any] = {
    "disabled": False,
    "print_call_link": False,
    "log_level": "CRITICAL",
    "capture_code": False,
    "implicitly_patch_integrations": False,
    "capture_client_info": False,
    "capture_system_info": False,
    "use_server_cache": False,
    "enable_disk_fallback": False,
    "enable_wal": False,
    # SDK 0.53.9 interprets this as total attempts, so 1 means zero retries.
    "retry_max_attempts": 1,
    "http_timeout": 20.0,
    "use_stainless_server": False,
}


@contextmanager
def quiet_sdk_output() -> Iterator[None]:
    """Suppress SDK debug output and raw exception text in this standalone CLI."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous)


@contextmanager
def _weave_environment(settings: Settings) -> Iterator[None]:
    # Weave reads credentials from the environment. Supply the explicitly loaded
    # key for this process only; never call wandb.login or write a global login.
    values: dict[str, str | None] = {
        "WANDB_API_KEY": settings.wandb_api_key,
        "WANDB_ENTITY": settings.wandb_entity,
        "WANDB_PROJECT": settings.wandb_project,
        "WANDB_BASE_URL": "https://api.wandb.ai",
        "WANDB_PUBLIC_BASE_URL": "https://wandb.ai",
        "WANDB_IDENTITY_TOKEN_FILE": None,
        "WANDB_ERROR_REPORTING": "false",
        "WF_TRACE_SERVER_URL": "https://trace.wandb.ai",
        "WEAVE_INSECURE_DISABLE_SSL": "false",
        "WEAVE_DEBUG_HTTP": "0",
    }
    # Environment variables override SDK settings. Pin both for this check so
    # inherited shell settings cannot turn code capture or retries back on.
    # String settings are case-sensitive (CRITICAL is a logging level, while
    # logging.critical is a function). Only boolean wire values are lowercase.
    values.update({f"WEAVE_{key.upper()}": str(value).lower() if isinstance(value, bool) else str(value)
                   for key, value in WEAVE_SETTINGS.items()})
    original = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def trace_request(settings: Settings, request: Callable[[], str]) -> tuple[str, str]:
    settings.require_wandb(require_model=True)
    with quiet_sdk_output(), _weave_environment(settings):
        import weave

        client = None
        outcome: dict[str, Any] | None = None
        try:
            client = weave.init(settings.project_path, settings=WEAVE_SETTINGS)

            @weave.op(name="faultlab_connection_check")
            def connection_check(model: str) -> dict[str, Any]:
                # Only model is an input. Code capture and automatic SDK patching
                # are disabled; credentials/client/settings are never serialized.
                try:
                    return {"ok": True, "response": request()}
                except Exception:
                    # Do not let raw provider exceptions enter Weave's serializer.
                    return {"ok": False, "error": "Inference request failed; no retry was made."}

            outcome, call = connection_check.call(settings.wandb_model)
            client.flush()
            if call is None or not call.id:
                raise ValueError("No call ID")
            # Flush can complete after a background upload failed. Read it back
            # from the server before claiming a real, completed trace exists.
            saved = client.get_call(call.id)
            if (
                saved.id != call.id
                or saved.project_id != settings.project_path
                or saved.ended_at is None
            ):
                raise ValueError("Trace was not persisted")
            if not outcome or not outcome.get("ok"):
                raise ProviderCheckError(
                    "Inference request failed. Check the verified model, credits, and access; no retry was made."
                )
            return outcome["response"], call.ui_url
        except ProviderCheckError:
            raise
        except Exception:
            response = outcome.get("response") if outcome and outcome.get("ok") else None
            raise ProviderCheckError(
                "Weave initialization or trace verification failed; no successful trace is claimed. Generation was not retried.",
                response=response,
            ) from None
        finally:
            if client is not None:
                try:
                    weave.finish()
                except Exception:
                    # The explicit flush/read above determines upload success.
                    pass
