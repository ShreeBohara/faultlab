"""W&B's documented OpenAI-compatible API, used only by the explicit CLI."""

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.providers import ProviderCheckError, redact_text
from app.providers.weave_tracing import quiet_sdk_output, trace_request

BASE_URL = "https://api.inference.wandb.ai/v1"
TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_TOKENS = 32
CHECK_PROMPT = "Reply with only: FaultLab connection OK"


def model_request_options(model: str) -> dict:
    """Documented model-specific settings, shared by smoke and campaign calls."""
    if model == "deepseek-ai/DeepSeek-V4-Pro-0813":
        # W&B enables thinking by default for this model. FaultLab consumes the
        # final structured answer, so do not spend its output allowance thinking.
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    return {}


@dataclass(frozen=True)
class GenerationResult:
    response: str
    trace_url: str


def _client(settings: Settings) -> Any:
    from openai import OpenAI

    return OpenAI(
        base_url=BASE_URL,
        api_key=settings.wandb_api_key,
        project=settings.project_path,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )


def _model_ids(client: Any, settings: Settings) -> list[str]:
    try:
        # Read this response's data, avoiding SDK auto-pagination/repeated requests.
        models = client.models.list().data
        ids = sorted({item.id for item in models if isinstance(item.id, str)})
        if any(
            secret and secret in model
            for model in ids
            for secret in (settings.wandb_api_key, settings.typesafe_api_key)
        ):
            raise ValueError("Unexpected model-list response")
        return ids
    except Exception:
        raise ProviderCheckError(
            "Could not list W&B models. Check credentials, entity access, and network; no retries were made."
        ) from None


def list_models(settings: Settings) -> list[str]:
    """One model-list request; no generation request or Weave initialization."""
    settings.require_wandb()
    with quiet_sdk_output():
        try:
            with _client(settings) as client:
                return _model_ids(client, settings)
        except ProviderCheckError:
            raise
        except Exception:
            raise ProviderCheckError("Could not initialize the W&B inference client.") from None


def generate_once(settings: Settings, *, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> GenerationResult:
    """Verify the model, then make one explicitly bounded traced generation."""
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 2000:
        raise ProviderCheckError("The output-token limit must be an integer from 1 to 2000.")
    settings.require_wandb(require_model=True)
    with quiet_sdk_output():
        try:
            with _client(settings) as client:
                if settings.wandb_model not in _model_ids(client, settings):
                    raise ProviderCheckError(
                        "WANDB_MODEL is not in the available model list. Run --list-models and save an exact available ID locally."
                    )

                def request() -> str:
                    completion = client.chat.completions.create(
                        model=settings.wandb_model,
                        messages=[{"role": "user", "content": CHECK_PROMPT}],
                        max_tokens=max_output_tokens,
                        stream=False,
                        **model_request_options(settings.wandb_model),
                    )
                    content = completion.choices[0].message.content
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("No text returned")
                    return redact_text(
                        content, settings.wandb_api_key, settings.typesafe_api_key
                    )

                response, trace_url = trace_request(settings, request)
                return GenerationResult(response=response, trace_url=trace_url)
        except ProviderCheckError:
            raise
        except Exception:
            raise ProviderCheckError(
                "W&B connection check failed. Check configuration and network; generation was not retried."
            ) from None
