import asyncio
import logging
import os
import json
from types import SimpleNamespace

import pytest

import check_provider
from app.config import Settings
from app.contracts.tokens import input_token_bound
from app.providers.runtime import RuntimeProvider, RuntimeProviderError


def test_preflight_does_not_load_settings(monkeypatch, capsys):
    monkeypatch.setattr(Settings, "from_env", lambda **_: pytest.fail("Read settings during offline preflight"))
    assert check_provider.main(["preflight"]) == 0
    assert '"provider_calls": 0' in capsys.readouterr().out


def test_runtime_missing_authorization_is_offline():
    client = RuntimeProvider(Settings(), client_factory=lambda **_: pytest.fail("Created unauthorized client"))
    with pytest.raises(RuntimeProviderError, match="explicit bounded"):
        asyncio.run(client.complete([{"role": "user", "content": "hello"}]))


def test_runtime_explicit_attribution_redaction_and_no_global_mutations():
    calls, options = [], {}
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hello fixture-private-key"))],
                               usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3))
    async def close(): pass
    def factory(**kwargs):
        options.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=close)
    settings = Settings(wandb_api_key="fixture-private-key", wandb_entity="fixture", wandb_project="project", wandb_model="model")
    env, logging_level = dict(os.environ), logging.root.manager.disable
    async def run():
        async with RuntimeProvider(settings, live_authorized=True, client_factory=factory) as provider:
            return await provider.complete([{"role": "user", "content": "hello"}], role="mechanic")
    result = asyncio.run(run())
    assert options["project"] == "fixture/project" and options["max_retries"] == 0
    assert len(calls) == 1 and calls[0]["max_tokens"] == 2000
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["temperature"] == 0
    assert result.model_id == "model" and result.input_tokens == 4 and result.cost_usd is None
    assert "fixture-private-key" not in result.content
    assert dict(os.environ) == env and logging.root.manager.disable == logging_level


def test_runtime_error_sanitized_without_retry():
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("Authorization: secret fixture key")
    provider = RuntimeProvider(Settings(wandb_api_key="key", wandb_entity="fixture", wandb_project="project", wandb_model="model"),
        live_authorized=True, client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(RuntimeProviderError) as caught:
        asyncio.run(provider.complete([{"role": "user", "content": "hello"}]))
    assert "secret" not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("model,content", [("unregistered-model", "x" * 32001), ("openai/gpt-oss-120b", "word " * 32000)])
def test_runtime_input_limit_precedes_client(model, content):
    messages = [{"role": "user", "content": content}]
    assert input_token_bound(messages, model) > 32000
    provider = RuntimeProvider(Settings(wandb_api_key="key", wandb_entity="fixture", wandb_project="project", wandb_model=model),
                               live_authorized=True, client_factory=lambda **_: pytest.fail("Client before input validation"))
    with pytest.raises(RuntimeProviderError, match="32,000-token"):
        asyncio.run(provider.complete(messages))


def test_runtime_token_admission_preserves_large_byte_prompt_without_truncation():
    messages = [{"role": "user", "content": "word " * 2500}]
    assert len(messages[0]["content"].encode()) > 8000
    assert input_token_bound(messages, "openai/gpt-oss-120b") < 8000
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="fixture result"))], usage=None)
    provider = RuntimeProvider(Settings(wandb_api_key="fixture-private-key", wandb_entity="fixture", wandb_project="project",
                                        wandb_model="openai/gpt-oss-120b"), live_authorized=True,
        client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = asyncio.run(provider.complete(messages))
    assert calls[0]["messages"] == messages and result.content == "fixture result"


def test_empty_final_response_retains_actual_usage_without_reasoning_or_retry():
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="length",
            message=SimpleNamespace(content=None, reasoning="private model reasoning must never be captured"))],
            usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=2000))
    provider = RuntimeProvider(Settings(wandb_api_key="fixture-private-key", wandb_entity="fixture", wandb_project="project",
        wandb_model="openai/gpt-oss-120b"), live_authorized=True,
        client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(RuntimeProviderError) as caught:
        asyncio.run(provider.complete([{"role": "user", "content": "fixture"}]))
    error = caught.value
    assert error.code == "EMPTY_FINAL_RESPONSE" and error.generation.content == ""
    assert error.diagnostics == {"code": "EMPTY_FINAL_RESPONSE", "error_class": "ValueError", "http_status": None,
                                 "finish_reason": "length", "input_tokens": 1200, "output_tokens": 2000}
    assert len(calls) == 1 and "private" not in json.dumps(error.diagnostics)


def test_real_sdk_http_error_keeps_only_safe_status_and_class():
    import httpx
    import openai
    async def create(**kwargs):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.inference.wandb.ai/v1/chat/completions",
                                                           headers={"Authorization": "Bearer fixture-private-key"}))
        raise openai.RateLimitError("fixture-private-key must not leak", response=response,
                                   body={"secret": "fixture-private-key", "reasoning": "hidden"})
    provider = RuntimeProvider(Settings(wandb_api_key="fixture-private-key", wandb_entity="fixture", wandb_project="project", wandb_model="model"),
        live_authorized=True, client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(RuntimeProviderError) as caught:
        asyncio.run(provider.complete([{"role": "user", "content": "fixture"}]))
    error = caught.value
    assert error.code == "HTTP_ERROR" and error.generation is None
    assert error.diagnostics["http_status"] == 429 and error.diagnostics["error_class"] == "RateLimitError"
    assert "fixture-private-key" not in str(error) + json.dumps(error.diagnostics)


def test_unrecognized_exception_and_finish_text_never_enter_diagnostics():
    error = RuntimeProviderError("Safe explanation", error_class="secret-in-class-name", http_status="429",
                                 finish_reason="secret-in-finish-reason")
    assert error.diagnostics["error_class"] == "ProviderError"
    assert error.diagnostics["http_status"] is None and error.diagnostics["finish_reason"] is None
    assert "secret" not in json.dumps(error.diagnostics)


@pytest.mark.parametrize('model,thinking_disabled', [
    ('deepseek-ai/DeepSeek-V4-Pro-0813', True),
    ('deepseek-ai/DeepSeek-V3.1', False),
    ('meta-llama/Llama-3.3-70B-Instruct', False),
    ('openai/gpt-oss-120b', False),
])
def test_documented_thinking_setting_matches_frozen_request(model, thinking_disabled):
    from app.providers.runtime import model_request_settings
    from app.lab.configuration import frozen_configuration
    from app.contracts.models import CampaignBudget
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
    settings = Settings(wandb_api_key='fixture-key', wandb_entity='fixture', wandb_project='project', wandb_model=model)
    provider = RuntimeProvider(settings, live_authorized=True,
        client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    asyncio.run(provider.complete([{'role': 'user', 'content': 'Return JSON.'}]))
    frozen = frozen_configuration(settings, CampaignBudget(), 'live-v1')['model_settings']
    assert frozen == model_request_settings(model)
    if thinking_disabled:
        expected = {'chat_template_kwargs': {'enable_thinking': False}}
        assert calls[0]['extra_body'] == frozen['extra_body'] == expected
    else:
        assert 'extra_body' not in calls[0] and 'extra_body' not in frozen


def test_runtime_dispatches_frozen_model_by_role():
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))],usage=None)
    settings=Settings(
        wandb_api_key='fixture-key',wandb_entity='fixture',wandb_project='project',
        wandb_model='meta-llama/Llama-3.1-8B-Instruct',
        wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813',
        wandb_mechanic_model='deepseek-ai/DeepSeek-V4-Pro-0813')
    provider=RuntimeProvider(settings,live_authorized=True,
        client_factory=lambda **_:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    async def run():
        return [
            await provider.complete([{'role':'user','content':'actor'}],role='actor'),
            await provider.complete([{'role':'user','content':'explorer'}],role='explorer'),
            await provider.complete([{'role':'user','content':'mechanic'}],role='mechanic'),
        ]
    generations=asyncio.run(run())
    assert [generation.model_id for generation in generations]==[
        'meta-llama/Llama-3.1-8B-Instruct',
        'deepseek-ai/DeepSeek-V4-Pro-0813',
        'deepseek-ai/DeepSeek-V4-Pro-0813']
    assert [call['model'] for call in calls]==[generation.model_id for generation in generations]
    assert 'extra_body' not in calls[0]
    assert all(call['extra_body']=={'chat_template_kwargs':{'enable_thinking':False}} for call in calls[1:])
