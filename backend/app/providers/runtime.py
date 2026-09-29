"""Explicit, asynchronous W&B inference for bounded campaign actions.

Unlike the standalone checker, this module never changes process environment,
logging, stdout, or SDK instrumentation. Clients are private and lazily created.
"""

import asyncio
from dataclasses import dataclass
import json
from typing import Any, Callable, Literal

from app.config import Settings
from app.contracts.models import (MODEL_INPUT_TOKEN_LIMIT, MODEL_OUTPUT_TOKEN_LIMIT, ReportAction, StrictModel,
                                  TaskReport, canonical_json, content_hash)
from app.contracts.tokens import validate_model_input
from app.providers import redact_text
from app.providers.wandb_inference import BASE_URL, model_request_options

MODEL_REQUEST_SETTINGS = {"max_input_tokens": MODEL_INPUT_TOKEN_LIMIT,
                          "max_output_tokens": MODEL_OUTPUT_TOKEN_LIMIT, "timeout_seconds": 20, "retries": 0,
                          "response_format": {"type": "json_object"}, "temperature": 0}
ACTOR_RESPONSE_PROTOCOL_VERSION = "faultlab-reference-final-report/v1"
ACTOR_FINAL_REPORT_SCHEMA_JSON = canonical_json(ReportAction.model_json_schema())


class NativeFinalAnswerArguments(StrictModel):
    answer: TaskReport


class NativeFinalAnswer(StrictModel):
    """The native smolagents final_answer action, exactly as the native transport carries it."""
    name: Literal["final_answer"]
    arguments: NativeFinalAnswerArguments


# Native adapter v2's reserved final-report turn (app.integrations.external_agent_v2). A separate,
# declared contract beside the reference Actor's: it leaves "actor_final_report" byte-identical.
NATIVE_FINAL_ANSWER_CONTRACT = "native_final_answer"
NATIVE_FINAL_ANSWER_PROTOCOL_VERSION = "faultlab-native-final-answer/v1"
NATIVE_FINAL_ANSWER_SCHEMA_JSON = canonical_json(NativeFinalAnswer.model_json_schema())
ResponseContract = Literal["actor_final_report", "native_final_answer"]


def response_format_for(*, role: str = "actor", response_contract: ResponseContract | None = None) -> dict:
    """Only reviewed code may select one of the fixed final-report contracts."""
    if response_contract is None:
        return {"type": "json_object"}
    if role != "actor" or response_contract not in ("actor_final_report", NATIVE_FINAL_ANSWER_CONTRACT):
        raise RuntimeProviderError("Unknown or role-incompatible response contract.", code="INVALID_INPUT")
    if response_contract == NATIVE_FINAL_ANSWER_CONTRACT:
        return {"type": "json_schema", "json_schema": {
            "name": "FaultLabNativeFinalAnswer", "strict": True,
            "schema": json.loads(NATIVE_FINAL_ANSWER_SCHEMA_JSON)}}
    return {"type": "json_schema", "json_schema": {
        "name": "FaultLabActorFinalReport", "strict": True,
        "schema": json.loads(ACTOR_FINAL_REPORT_SCHEMA_JSON)}}


def actor_response_protocol() -> dict:
    final_format = response_format_for(response_contract="actor_final_report")
    return {"version": ACTOR_RESPONSE_PROTOCOL_VERSION, "scope": "faultlab_reference_actor",
            "trigger": "EpisodeMeter.final_turn: reserved last turn or business_closed",
            "response_contract": "actor_final_report", "response_format": final_format,
            "schema_hash": content_hash(final_format["json_schema"]["schema"]),
            "response_format_hash": content_hash(final_format),
            "input_admission": "messages_plus_final_report_response_format/v1"}


def native_final_answer_protocol() -> dict:
    """Declared structured-output contract of native adapter v2's final-report turn (not the reference Actor's)."""
    final_format = response_format_for(response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
    return {"version": NATIVE_FINAL_ANSWER_PROTOCOL_VERSION, "scope": "smolagents_native_adapter_v2",
            "trigger": "EpisodeMeter.final_turn: reserved last turn or business_closed",
            "response_contract": NATIVE_FINAL_ANSWER_CONTRACT, "response_format": final_format,
            "schema_hash": content_hash(final_format["json_schema"]["schema"]),
            "response_format_hash": content_hash(final_format),
            "input_admission": "messages_plus_final_report_response_format/v1"}


def validate_request_input(messages, model: str, *, role: str = "actor",
                           response_contract: ResponseContract | None = None) -> int:
    """Admit the final-report schema without changing the sent messages.

    An admission-only message counts serialized schema tokens and conservatively
    reserves message framing. It is never sent to the model or added to history.
    Default JSON mode keeps the existing admission and its framing reserve, so
    other callers' pre-debit admission remains identical to provider admission.
    """
    if response_contract is None:
        return validate_model_input(messages, model)
    response_format = response_format_for(role=role, response_contract=response_contract)
    return validate_model_input([*messages, {"role": "system", "content": canonical_json({
        "response_format": response_format})}], model)


def model_request_settings(model: str) -> dict:
    return {**MODEL_REQUEST_SETTINGS, **model_request_options(model)}


class RuntimeProviderError(RuntimeError):
    """Safe failure metadata; never retain a response, raw SDK error, or reasoning."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR", error_class: str | None = None,
                 http_status: int | None = None, finish_reason: str | None = None, generation=None):
        super().__init__(message)
        self.code = code if code in {
            "PROVIDER_ERROR", "EMPTY_FINAL_RESPONSE", "INVALID_RESPONSE_SHAPE", "REQUEST_TIMEOUT",
            "HTTP_ERROR", "CONNECTION_ERROR", "LIVE_ACTION_REQUIRED", "INVALID_ROLE", "REQUEST_LIMIT",
            "INVALID_INPUT", "INPUT_LIMIT", "SECRET_INPUT"} else "PROVIDER_ERROR"
        self.error_class = error_class if error_class in {
            "APIConnectionError", "APITimeoutError", "RateLimitError", "BadRequestError", "AuthenticationError",
            "PermissionDeniedError", "NotFoundError", "ConflictError", "UnprocessableEntityError",
            "InternalServerError", "APIStatusError", "TimeoutError", "ValueError", "IndexError", "TypeError",
            "AttributeError", "RuntimeError"} else "ProviderError"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
        self.finish_reason = finish_reason if isinstance(finish_reason, str) and finish_reason in {"stop", "length", "tool_calls", "content_filter", "function_call"} else None
        self.generation = generation

    @property
    def diagnostics(self) -> dict:
        return {"code": self.code, "error_class": self.error_class, "http_status": self.http_status,
                "finish_reason": self.finish_reason,
                "input_tokens": self.generation.input_tokens if self.generation else None,
                "output_tokens": self.generation.output_tokens if self.generation else None}


@dataclass(frozen=True)
class RuntimeGeneration:
    content: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class RuntimeProvider:
    def __init__(self, settings: Settings, *, live_authorized: bool = False,
                 client_factory: Callable[..., Any] | None = None):
        self._settings = settings
        self._authorized = live_authorized
        self._factory = client_factory
        self._clients = {}

    def role_model(self, role: str) -> str:
        """Frozen model for a runtime role; Explorer/Mechanic may use the lab model."""
        return self._settings.model_for(role)

    async def complete(self, messages: list[dict[str, str]], *, role: str = "actor",
                       max_output_tokens: int = MODEL_OUTPUT_TOKEN_LIMIT, timeout_seconds: float = 20.0,
                       response_contract: ResponseContract | None = None) -> RuntimeGeneration:
        if not self._authorized:
            raise RuntimeProviderError("An explicit bounded live action is required.", code="LIVE_ACTION_REQUIRED")
        self._settings.require_wandb(require_model=True)
        if role not in {"actor", "explorer", "mechanic"}:
            raise RuntimeProviderError("Unknown runtime role.", code="INVALID_ROLE")
        model=self._settings.model_for_role(role)
        if not 1 <= max_output_tokens <= MODEL_OUTPUT_TOKEN_LIMIT or not 0 < timeout_seconds <= 20:
            raise RuntimeProviderError("Model request exceeds the frozen per-call limits.", code="REQUEST_LIMIT")
        if not messages or any(set(m) != {"role", "content"} or m["role"] not in {"system", "user", "assistant"}
                               or not isinstance(m["content"], str) for m in messages):
            raise RuntimeProviderError("Invalid model input.", code="INVALID_INPUT")
        model = self.role_model(role)
        response_format = response_format_for(role=role, response_contract=response_contract)
        try:
            validate_request_input(messages, model, role=role, response_contract=response_contract)
        except ValueError:
            raise RuntimeProviderError(f"Model input exceeds or cannot verify the frozen {MODEL_INPUT_TOKEN_LIMIT:,}-token bound.", code="INPUT_LIMIT") from None
        secrets = (self._settings.wandb_api_key, self._settings.typesafe_api_key)
        if any(secret and secret in json.dumps(messages) for secret in secrets):
            raise RuntimeProviderError("Secret-bearing model input was rejected.", code="SECRET_INPUT")
        returned_usage = None
        finish_reason = None
        try:
            if model not in self._clients:
                if self._factory is None:
                    from openai import AsyncOpenAI
                    factory = AsyncOpenAI
                else:
                    factory = self._factory
                self._clients[model] = factory(base_url=BASE_URL, api_key=self._settings.wandb_api_key,
                                               project=self._settings.project_path, timeout=timeout_seconds, max_retries=0)
            client=self._clients[model]
            async with asyncio.timeout(timeout_seconds):
                response = await client.chat.completions.create(
                    model=model, messages=messages, max_tokens=max_output_tokens,
                    response_format=response_format,
                    temperature=MODEL_REQUEST_SETTINGS["temperature"], stream=False, timeout=timeout_seconds,
                    **model_request_options(model))
            usage = getattr(response, "usage", None)
            def token_count(name):
                value = getattr(usage, name, None)
                return value if type(value) is int and 0 <= value <= 1_000_000_000 else None
            # This is usage from an actual response, not a fabricated actor answer.
            # Preserve it even if no final content survives the output-token cap.
            returned_usage = RuntimeGeneration(content="", model_id=model,
                input_tokens=token_count("prompt_tokens"), output_tokens=token_count("completion_tokens"))
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            content = choice.message.content
            if not isinstance(content, str) or not content.strip():
                raise RuntimeProviderError("W&B returned no final response; no generation retry was made.",
                    code="EMPTY_FINAL_RESPONSE", error_class="ValueError", finish_reason=finish_reason, generation=returned_usage)
            return RuntimeGeneration(
                content=redact_text(content, *secrets), model_id=model,
                input_tokens=returned_usage.input_tokens, output_tokens=returned_usage.output_tokens)
        except asyncio.CancelledError:
            raise
        except RuntimeProviderError:
            raise
        except Exception as error:
            status = getattr(error, "status_code", None)
            error_name = type(error).__name__
            code = ("REQUEST_TIMEOUT" if isinstance(error, TimeoutError) or error_name == "APITimeoutError" else
                    "HTTP_ERROR" if type(status) is int and 100 <= status <= 599 else
                    "CONNECTION_ERROR" if error_name == "APIConnectionError" else
                    "INVALID_RESPONSE_SHAPE" if returned_usage is not None else "PROVIDER_ERROR")
            raise RuntimeProviderError("W&B inference failed; no generation retry was made.", code=code,
                error_class=error_name, http_status=status, finish_reason=finish_reason, generation=returned_usage) from None

    async def close(self) -> None:
        clients=list(self._clients.values())
        self._clients.clear()
        for client in clients:
            try:
                await client.close()
            except Exception:
                pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
