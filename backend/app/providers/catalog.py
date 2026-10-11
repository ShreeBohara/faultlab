"""Model providers FaultLab can call, and how each one must be asked.

A model is named by a *reference* of the form ``provider:model_id``. An unprefixed name
belongs to the configured default provider (``FAULTLAB_DEFAULT_PROVIDER``, ``wandb`` unless
changed), so every pre-existing configuration keeps its meaning.

Every provider speaks the OpenAI chat-completions wire format through the official OpenAI
SDK, but they differ in what they accept. Those differences are *request profiles* and are
frozen into a campaign's configuration beside the model name, so two runs that sent
different parameters never share an identity:

* W&B Inference accepts ``max_tokens``, ``temperature`` and JSON response formats, and needs
  ``chat_template_kwargs`` to disable DeepSeek V4 thinking (``wandb_inference.model_request_options``).
* OpenAI accepts ``max_completion_tokens`` on every chat model; its reasoning models
  (``gpt-5*``, ``gpt-6*``, ``o*``) reject ``temperature``, so it is omitted for them.
* Anthropic's OpenAI-compatible layer ignores ``response_format`` entirely and returns 400
  for ``temperature`` below 1 on current models, so neither is sent and structured output is
  recorded as *not enforced* (the prompts already ask for JSON; the lab validates every answer).
* OpenRouter forwards ``response_format`` and returns a per-call ``usage.cost``; vendor
  parameter rules apply by model prefix (``anthropic/...``, ``openai/gpt-5...``).
* ``custom`` is any OpenAI-compatible endpoint the operator names.

Importing this module performs no I/O and creates no client.
"""

from dataclasses import dataclass
from typing import Any, Literal

ProviderId = Literal["wandb", "openai", "anthropic", "openrouter", "custom"]
PROVIDER_IDS: tuple[str, ...] = ("wandb", "openai", "anthropic", "openrouter", "custom")

WANDB_BASE_URL = "https://api.inference.wandb.ai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Documented on 2026-10-10: platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk
# ("response_format: Ignored"; "temperature ... On Claude 4.7 and later models ... any value
# below 1 returns a 400 error, so omit it") and developers.openai.com/api/docs/guides/reasoning.
_OPENAI_REASONING_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4", "o5")


class UnknownProviderError(ValueError):
    """A model reference names a provider FaultLab does not know."""


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model_id: str

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.model_id}"


def parse_model_ref(name: str, default_provider: str = "wandb") -> ModelRef:
    """Split ``provider:model`` into its parts; an unprefixed name uses the default provider.

    Model ids may themselves contain ``/`` (``deepseek-ai/DeepSeek-V3.1``) and ``:``
    (OpenRouter variants such as ``model:free``), so only a *known* provider prefix is split.
    """
    if not isinstance(name, str) or not name.strip():
        raise UnknownProviderError("A model reference must be a non-empty string.")
    name = name.strip()
    head, separator, tail = name.partition(":")
    if separator and head in PROVIDER_IDS and tail.strip():
        return ModelRef(provider=head, model_id=tail.strip())
    if default_provider not in PROVIDER_IDS:
        raise UnknownProviderError(f"Unknown default provider '{default_provider}'.")
    return ModelRef(provider=default_provider, model_id=name)


def canonical_model_name(name: str, default_provider: str = "wandb") -> str:
    """The one spelling of a model name that settings and frozen configurations record.

    W&B models keep their historical bare ids (``deepseek-ai/DeepSeek-V3.1``), so every campaign
    frozen before other providers existed keeps its identity. Any other provider is always spelled
    out (``openai:gpt-5-mini``), whatever default provider the writing machine had, so a recorded
    name never depends on that machine's settings. A blank name stays blank.
    """
    if not isinstance(name, str) or not name.strip():
        return ""
    ref = parse_model_ref(name, default_provider)
    return ref.model_id if ref.provider == "wandb" else ref.ref


def _openai_supports_temperature(model_id: str) -> bool:
    lowered = model_id.lower()
    if "chat" in lowered:
        return True
    return not lowered.startswith(_OPENAI_REASONING_PREFIXES)


@dataclass(frozen=True)
class RequestProfile:
    """How a provider must be asked; frozen into every configuration that uses it."""
    provider: str
    token_limit_parameter: Literal["max_tokens", "max_completion_tokens"]
    temperature: int | float | None      # None: the parameter is omitted from the request
    response_format_enforced: bool       # False: the API ignores response_format, so it is not sent
    extra_body: dict[str, Any] | None = None

    def request_kwargs(self, *, max_output_tokens: int, response_format: dict) -> dict[str, Any]:
        kwargs: dict[str, Any] = {self.token_limit_parameter: max_output_tokens}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.response_format_enforced:
            kwargs["response_format"] = response_format
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        return kwargs

    def frozen(self) -> dict[str, Any]:
        settings: dict[str, Any] = {"provider": self.provider,
                                    "token_limit_parameter": self.token_limit_parameter,
                                    "temperature": self.temperature,
                                    "response_format_enforced": self.response_format_enforced}
        if self.extra_body:
            settings["extra_body"] = self.extra_body
        return settings


def request_profile(ref: ModelRef) -> RequestProfile:
    """The documented parameter rules for one provider and model, decided by fixed code."""
    model = ref.model_id
    if ref.provider == "wandb":
        from app.providers.wandb_inference import model_request_options
        options = model_request_options(model)
        return RequestProfile("wandb", "max_tokens", 0, True, options.get("extra_body"))
    if ref.provider == "openai":
        return RequestProfile("openai", "max_completion_tokens",
                              0 if _openai_supports_temperature(model) else None, True)
    if ref.provider == "anthropic":
        return RequestProfile("anthropic", "max_tokens", None, False)
    if ref.provider == "openrouter":
        vendor, _, vendor_model = model.partition("/")
        if vendor == "anthropic":
            temperature = None
        elif vendor == "openai":
            temperature = 0 if _openai_supports_temperature(vendor_model) else None
        else:
            temperature = 0
        return RequestProfile("openrouter", "max_tokens", temperature, True)
    if ref.provider == "custom":
        return RequestProfile("custom", "max_tokens", 0, True)
    raise UnknownProviderError(f"Unknown provider '{ref.provider}'.")


@dataclass(frozen=True)
class ProviderClientSpec:
    """Everything needed to build one SDK client for a provider; never logged or traced."""
    provider: str
    base_url: str
    api_key: str
    client_kwargs: dict[str, Any]
    missing: tuple[str, ...]            # configuration names that are blank, by setting name

    @property
    def configured(self) -> bool:
        return not self.missing


def client_spec(ref: ModelRef, settings) -> ProviderClientSpec:
    """Resolve base URL, key and client options for a provider from explicit settings."""
    if ref.provider == "wandb":
        missing = tuple(name.upper() for name in ("wandb_api_key", "wandb_entity", "wandb_project")
                        if not getattr(settings, name).strip())
        return ProviderClientSpec("wandb", WANDB_BASE_URL, settings.wandb_api_key,
                                  {"project": settings.project_path}, missing)
    if ref.provider == "openai":
        missing = () if settings.openai_api_key.strip() else ("OPENAI_API_KEY",)
        return ProviderClientSpec("openai", OPENAI_BASE_URL, settings.openai_api_key, {}, missing)
    if ref.provider == "anthropic":
        missing = () if settings.anthropic_api_key.strip() else ("ANTHROPIC_API_KEY",)
        # Anthropic returns 400 for an organization-scoped key unless every request names the workspace.
        workspace = settings.anthropic_workspace_id.strip()
        options = {"default_headers": {"anthropic-workspace-id": workspace}} if workspace else {}
        return ProviderClientSpec("anthropic", ANTHROPIC_BASE_URL, settings.anthropic_api_key, options, missing)
    if ref.provider == "openrouter":
        missing = () if settings.openrouter_api_key.strip() else ("OPENROUTER_API_KEY",)
        headers = {"HTTP-Referer": "https://github.com/ShreeBohara/faultlab", "X-Title": "FaultLab"}
        return ProviderClientSpec("openrouter", OPENROUTER_BASE_URL, settings.openrouter_api_key,
                                  {"default_headers": headers}, missing)
    if ref.provider == "custom":
        missing = tuple(name for name, value in (("FAULTLAB_CUSTOM_BASE_URL", settings.faultlab_custom_base_url),
                                                   ("FAULTLAB_CUSTOM_API_KEY", settings.faultlab_custom_api_key))
                        if not value.strip())
        return ProviderClientSpec("custom", settings.faultlab_custom_base_url.strip(),
                                  settings.faultlab_custom_api_key, {}, missing)
    raise UnknownProviderError(f"Unknown provider '{ref.provider}'.")


def provider_secrets(settings) -> tuple[str, ...]:
    """Every credential that must be redacted from model output and errors."""
    return tuple(value for value in (settings.wandb_api_key, settings.typesafe_api_key, settings.openai_api_key,
                                     settings.anthropic_api_key, settings.openrouter_api_key,
                                     settings.faultlab_custom_api_key) if value)
