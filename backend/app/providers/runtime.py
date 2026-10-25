"""Explicit, asynchronous model inference for bounded campaign actions.

Unlike the standalone checker, this module never changes process environment,
logging, stdout, or SDK instrumentation. Clients are private and lazily created.

Every call is dispatched to the provider named by the role's model reference
(``provider:model_id``; see ``app.providers.catalog``) with that provider's documented
request profile, after input admission, credential checks, and a worst-case dollar
reservation against the monthly spend ledger when the model is priced.
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
from app.providers.catalog import (UnknownProviderError, client_spec, parse_model_ref, provider_secrets,
                                   request_profile)
from app.providers.spend import MonthlyCapExceeded, SpendLedger

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
    """The frozen per-call settings for a canonical model name (``Settings.model_for``).

    A W&B model (a bare id) keeps exactly the dict every earlier campaign recorded, so their
    identities survive. A model on another provider (``provider:model``) adds that provider's
    request profile: the provider, which token-limit parameter is sent, whether ``temperature`` is
    sent (None: omitted) and whether the API enforces ``response_format``.
    """
    if not isinstance(model, str) or not model.strip():
        return dict(MODEL_REQUEST_SETTINGS)
    ref = parse_model_ref(model)
    profile = request_profile(ref)
    settings = dict(MODEL_REQUEST_SETTINGS)
    if profile.extra_body:
        settings["extra_body"] = profile.extra_body
    if ref.provider != "wandb":
        settings.update(provider=ref.provider, token_limit_parameter=profile.token_limit_parameter,
                        temperature=profile.temperature, response_format_enforced=profile.response_format_enforced)
    return settings


class RuntimeProviderError(RuntimeError):
    """Safe failure metadata; never retain a response, raw SDK error, or reasoning."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR", error_class: str | None = None,
                 http_status: int | None = None, finish_reason: str | None = None, generation=None):
        super().__init__(message)
        self.code = code if code in {
            "PROVIDER_ERROR", "EMPTY_FINAL_RESPONSE", "INVALID_RESPONSE_SHAPE", "REQUEST_TIMEOUT",
            "HTTP_ERROR", "CONNECTION_ERROR", "LIVE_ACTION_REQUIRED", "INVALID_ROLE", "REQUEST_LIMIT",
            "INVALID_INPUT", "INPUT_LIMIT", "SECRET_INPUT", "MONTHLY_CAP", "UNKNOWN_PROVIDER"} else "PROVIDER_ERROR"
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
    provider: str | None = None
    structured_output_enforced: bool = True


def _token_count(usage, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def _reported_cost(usage) -> float | None:
    """A provider-reported per-call cost (OpenRouter's ``usage.cost``); never used for admission."""
    value = usage.get("cost") if isinstance(usage, dict) else getattr(usage, "cost", None)
    return float(value) if type(value) in (int, float) and 0 <= value < 1_000 else None


class RuntimeProvider:
    def __init__(self, settings: Settings, *, live_authorized: bool = False,
                 client_factory: Callable[..., Any] | None = None, spend_ledger: SpendLedger | None = None):
        self._settings = settings
        self._authorized = live_authorized
        self._factory = client_factory
        self._clients = {}
        self._ledger = spend_ledger
        self._workdir: str | None = None     # the Claude Code CLI's empty working directory, made on first use

    def role_model(self, role: str) -> str:
        """Frozen model for a runtime role; Explorer/Mechanic may use the lab model."""
        return self._settings.model_for(role)

    def _spend_ledger(self) -> SpendLedger:
        if self._ledger is None:
            self._ledger = SpendLedger(self._settings.spend_ledger_path)
        return self._ledger

    async def complete(self, messages: list[dict[str, str]], *, role: str = "actor",
                       max_output_tokens: int = MODEL_OUTPUT_TOKEN_LIMIT, timeout_seconds: float = 20.0,
                       response_contract: ResponseContract | None = None) -> RuntimeGeneration:
        if not self._authorized:
            raise RuntimeProviderError("An explicit bounded live action is required.", code="LIVE_ACTION_REQUIRED")
        if role not in {"actor", "explorer", "mechanic"}:
            raise RuntimeProviderError("Unknown runtime role.", code="INVALID_ROLE")
        try:
            # ConfigurationError (a blank model or blank credentials) propagates by name, as before.
            self._settings.require_provider(role)
            ref = self._settings.model_ref_for_role(role)
        except UnknownProviderError:
            raise RuntimeProviderError("The configured default provider is unknown.", code="UNKNOWN_PROVIDER") from None
        if not 1 <= max_output_tokens <= MODEL_OUTPUT_TOKEN_LIMIT or not 0 < timeout_seconds <= 20:
            raise RuntimeProviderError("Model request exceeds the frozen per-call limits.", code="REQUEST_LIMIT")
        if not messages or any(set(m) != {"role", "content"} or m["role"] not in {"system", "user", "assistant"}
                               or not isinstance(m["content"], str) for m in messages):
            raise RuntimeProviderError("Invalid model input.", code="INVALID_INPUT")
        model = self.role_model(role)
        profile = request_profile(ref)
        response_format = response_format_for(role=role, response_contract=response_contract)
        try:
            validate_request_input(messages, ref.model_id, role=role, response_contract=response_contract)
        except ValueError:
            raise RuntimeProviderError(f"Model input exceeds or cannot verify the frozen {MODEL_INPUT_TOKEN_LIMIT:,}-token bound.", code="INPUT_LIMIT") from None
        secrets = provider_secrets(self._settings)
        if any(secret and secret in json.dumps(messages) for secret in secrets):
            raise RuntimeProviderError("Secret-bearing model input was rejected.", code="SECRET_INPUT")
        spec = client_spec(ref, self._settings)
        rates = self._settings.model_rates_for_role(role)
        bound = self._settings.per_call_dollar_bound_for_role(role)
        charge_id = None
        if bound is not None:
            # A subscription call moves no money: the monthly ledger records it at zero with the API-equivalent
            # bound in the note, while the campaign ledger still charges the equivalent cost (shadow pricing).
            subscription = ref.provider == "claude-code"
            try:
                charge_id = self._spend_ledger().reserve(
                    provider=ref.provider, model=ref.ref, role=role, bound_usd=0.0 if subscription else bound,
                    cap_usd=self._settings.faultlab_monthly_dollar_cap,
                    note=f"subscription; api-equivalent bound {bound:.6f}" if subscription else "")
            except MonthlyCapExceeded as error:
                raise RuntimeProviderError(str(error), code="MONTHLY_CAP") from None
        if ref.provider == "claude-code":
            return await self._complete_via_claude_code(ref=ref, spec=spec, messages=messages, model=model, rates=rates,
                                                        charge_id=charge_id, max_output_tokens=max_output_tokens,
                                                        timeout_seconds=timeout_seconds, secrets=secrets)
        returned_usage = None
        finish_reason = None
        try:
            if ref.provider not in self._clients:
                if self._factory is None:
                    from openai import AsyncOpenAI
                    factory = AsyncOpenAI
                else:
                    factory = self._factory
                self._clients[ref.provider] = factory(base_url=spec.base_url, api_key=spec.api_key,
                                                      timeout=timeout_seconds, max_retries=0, **spec.client_kwargs)
            client = self._clients[ref.provider]
            async with asyncio.timeout(timeout_seconds):
                response = await client.chat.completions.create(
                    model=ref.model_id, messages=messages, stream=False, timeout=timeout_seconds,
                    **profile.request_kwargs(max_output_tokens=max_output_tokens, response_format=response_format))
            usage = getattr(response, "usage", None)
            input_tokens, output_tokens = _token_count(usage, "prompt_tokens"), _token_count(usage, "completion_tokens")
            # Measured cost: the provider's own per-call figure when it reports one (OpenRouter), else the
            # response's token counts at the verified rates. None stays None: nothing is ever estimated.
            cost = _reported_cost(usage) if ref.provider == "openrouter" else None
            if cost is None and rates is not None and input_tokens is not None and output_tokens is not None:
                cost = (input_tokens * rates[0] + output_tokens * rates[1]) / 1000000
            if charge_id is not None:
                self._spend_ledger().settle(charge_id, actual_usd=cost, input_tokens=input_tokens, output_tokens=output_tokens)
            # This is usage from an actual response, not a fabricated actor answer.
            # Preserve it even if no final content survives the output-token cap.
            returned_usage = RuntimeGeneration(content="", model_id=model, input_tokens=input_tokens,
                                               output_tokens=output_tokens, cost_usd=cost, provider=ref.provider,
                                               structured_output_enforced=profile.response_format_enforced)
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            content = choice.message.content
            if not isinstance(content, str) or not content.strip():
                raise RuntimeProviderError("The provider returned no final response; no generation retry was made.",
                    code="EMPTY_FINAL_RESPONSE", error_class="ValueError", finish_reason=finish_reason, generation=returned_usage)
            return RuntimeGeneration(
                content=redact_text(content, *secrets), model_id=model,
                input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost, provider=ref.provider,
                structured_output_enforced=profile.response_format_enforced)
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
            raise RuntimeProviderError("Model inference failed; no generation retry was made.", code=code,
                error_class=error_name, http_status=status, finish_reason=finish_reason, generation=returned_usage) from None

    async def _complete_via_claude_code(self, *, ref, spec, messages, model, rates, charge_id, max_output_tokens,
                                        timeout_seconds, secrets) -> RuntimeGeneration:
        """One bounded call through the Claude Code CLI on the owner's subscription (docs/providers.md).

        The CLI runs in a scrubbed environment (no API key can reach it, so the subscription is always what
        pays), with no setting sources, no tools, one turn, no session persistence, and the lab's system
        prompt in place of its own. The prompt goes in on stdin; the JSON result's usage and text come back.
        A transcript with assistant turns is rendered into the single prompt, which the frozen request
        profile records as the channel's behaviour. Nothing is retried.
        """
        import os
        import shutil
        import tempfile
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        if len(turns) == 1 and turns[0]["role"] == "user":
            prompt = turns[0]["content"]
        else:
            prompt = ("The conversation so far, oldest first. Continue it with your next reply only.\n\n"
                      + "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in turns))
        env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""), "USER": os.environ.get("USER", ""),
               "LANG": os.environ.get("LANG") or "en_US.UTF-8", "TERM": "dumb",
               "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(int(max_output_tokens)), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        for name in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN"):
            if os.environ.get(name):
                env[name] = os.environ[name]
        command = [spec.client_kwargs["binary"], "-p", "--model", ref.model_id, "--output-format", "json", "--tools", "",
                   "--max-turns", "1", "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
                   "--system-prompt", system]
        if self._workdir is None or not os.path.isdir(self._workdir):
            self._workdir = tempfile.mkdtemp(prefix="faultlab-claude-code-")
        failure = "Model inference failed; no generation retry was made."
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env, cwd=self._workdir)
        except (OSError, ValueError) as error:
            raise RuntimeProviderError(failure, code="CONNECTION_ERROR", error_class=type(error).__name__) from None
        try:
            async with asyncio.timeout(timeout_seconds):
                stdout, _stderr = await process.communicate(prompt.encode("utf-8"))
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeProviderError(failure, code="REQUEST_TIMEOUT", error_class="TimeoutError") from None
        try:
            result = json.loads(stdout.decode("utf-8", "replace"))
            if not isinstance(result, dict):
                raise ValueError("not an object")
        except ValueError:
            raise RuntimeProviderError(failure, code="INVALID_RESPONSE_SHAPE", error_class="ValueError") from None
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}

        def count(name):
            value = usage.get(name)
            return value if type(value) is int and 0 <= value <= 1_000_000_000 else None
        fresh = count("input_tokens")
        # Cache reads and writes are input the model saw; counting them in full keeps the equivalent cost an upper bound.
        input_tokens = None if fresh is None else fresh + (count("cache_creation_input_tokens") or 0) + (count("cache_read_input_tokens") or 0)
        output_tokens = count("output_tokens")
        cost = None
        if rates is not None and input_tokens is not None and output_tokens is not None:
            cost = (input_tokens * rates[0] + output_tokens * rates[1]) / 1000000
        if charge_id is not None:
            self._spend_ledger().settle(charge_id, actual_usd=0.0, input_tokens=input_tokens, output_tokens=output_tokens)
        returned = RuntimeGeneration(content="", model_id=model, input_tokens=input_tokens, output_tokens=output_tokens,
                                     cost_usd=cost, provider="claude-code", structured_output_enforced=False)
        if result.get("is_error") or result.get("subtype") not in (None, "success"):
            text = str(result.get("result") or "").lower()
            error_class = ("AuthenticationError" if "not logged in" in text or "login" in text else
                           "BadRequestError" if "too long" in text else
                           "RateLimitError" if "limit" in text else "RuntimeError")
            status = result.get("api_error_status")
            raise RuntimeProviderError(failure, code="PROVIDER_ERROR", error_class=error_class,
                                       http_status=status if type(status) is int else None, generation=returned)
        used = result.get("modelUsage") if isinstance(result.get("modelUsage"), dict) else {}
        if used and not any(key == ref.model_id or key.startswith(ref.model_id) for key in used):
            # The CLI answered with a model other than the one frozen into the campaign: not this identity.
            raise RuntimeProviderError(failure, code="INVALID_RESPONSE_SHAPE", error_class="ValueError", generation=returned)
        content = result.get("result")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeProviderError("The provider returned no final response; no generation retry was made.",
                                       code="EMPTY_FINAL_RESPONSE", error_class="ValueError", generation=returned)
        return RuntimeGeneration(content=redact_text(content, *secrets), model_id=model, input_tokens=input_tokens,
                                 output_tokens=output_tokens, cost_usd=cost, provider="claude-code",
                                 structured_output_enforced=False)

    async def close(self) -> None:
        clients = list(self._clients.values())
        self._clients.clear()
        if self._workdir is not None:
            import shutil
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None
        for client in clients:
            try:
                await client.close()
            except Exception:
                pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
