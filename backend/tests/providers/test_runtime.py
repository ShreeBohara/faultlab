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


def test_final_report_contract_uses_exact_schema_without_changing_request_or_answer():
    from app.contracts.models import ReportAction
    from app.providers.runtime import response_format_for
    calls=[]
    original='{"kind":"tool","tool":"get_order","arguments":{}}'
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=original))],usage=None)
    settings=Settings(wandb_api_key='fixture-key',wandb_entity='fixture',wandb_project='project',wandb_model='deepseek-ai/DeepSeek-V3.1')
    provider=RuntimeProvider(settings,live_authorized=True,
        client_factory=lambda **_:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    messages=[{'role':'user','content':'Report now.'}]
    returned=asyncio.run(provider.complete(messages,response_contract='actor_final_report'))
    assert len(calls)==1 and calls[0]['messages']==messages
    assert calls[0]['response_format']==response_format_for(response_contract='actor_final_report')
    assert calls[0]['response_format']['json_schema']['schema']==ReportAction.model_json_schema()
    assert calls[0]['response_format']['json_schema']['strict'] is True
    assert calls[0]['temperature']==0 and calls[0]['max_tokens']==2000
    # Even a provider which ignores its schema cannot trigger repair or fallback.
    assert returned.content==original


@pytest.mark.parametrize('role,contract',[
    ('explorer','actor_final_report'),('mechanic','actor_final_report'),
    ('actor','arbitrary_schema'),('actor',{'type':'json_schema'}),
])
def test_unreviewed_response_contract_rejected_before_client(role,contract):
    provider=RuntimeProvider(Settings(wandb_api_key='fixture-key',wandb_entity='fixture',wandb_project='project',wandb_model='model'),
        live_authorized=True,client_factory=lambda **_:pytest.fail('Client created for an unreviewed contract'))
    with pytest.raises(RuntimeProviderError) as error:
        asyncio.run(provider.complete([{'role':'user','content':'hello'}],role=role,response_contract=contract))
    assert error.value.code=='INVALID_INPUT'


def test_schema_tokens_rejected_before_client_when_messages_alone_fit():
    from app.providers.runtime import validate_request_input
    model='unregistered-byte-bound-model'
    messages=[{'role':'user','content':'x'*31700}]
    assert input_token_bound(messages,model)<32000
    assert validate_request_input(messages,model)==input_token_bound(messages,model)
    with pytest.raises(ValueError,match='32,000-token'):
        validate_request_input(messages,model,response_contract='actor_final_report')
    provider=RuntimeProvider(Settings(wandb_api_key='fixture-key',wandb_entity='fixture',wandb_project='project',wandb_model=model),
        live_authorized=True,client_factory=lambda **_:pytest.fail('Client created before complete input admission'))
    with pytest.raises(RuntimeProviderError) as error:
        asyncio.run(provider.complete(messages,response_contract='actor_final_report'))
    assert error.value.code=='INPUT_LIMIT'


def test_schema_rejection_never_retries_with_json_mode():
    calls=[]
    async def create(**kwargs):
        calls.append(kwargs)
        raise ValueError('Provider rejected the requested schema')
    provider=RuntimeProvider(Settings(wandb_api_key='fixture-key',wandb_entity='fixture',wandb_project='project',wandb_model='model'),
        live_authorized=True,client_factory=lambda **_:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(RuntimeProviderError):
        asyncio.run(provider.complete([{'role':'user','content':'Report now.'}],response_contract='actor_final_report'))
    assert len(calls)==1 and calls[0]['response_format']['type']=='json_schema'


# ---- Provider dispatch (Phase 0.5): one engine, several model providers ----

def _client(calls, content='{}', usage=None, finish_reason='stop'):
    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content=content))],
                               usage=usage)
    async def close(): pass
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=close)


def test_openai_models_get_their_documented_request_shape_and_keep_the_configured_name():
    calls, factories = [], []
    def factory(**kwargs):
        factories.append(kwargs)
        return _client(calls, usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))
    settings = Settings(openai_api_key='openai-private-key', faultlab_actor_model='openai:gpt-5-mini')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=factory)
    result = asyncio.run(provider.complete([{'role': 'user', 'content': 'hi'}]))
    assert factories == [{'base_url': 'https://api.openai.com/v1', 'api_key': 'openai-private-key', 'timeout': 20.0, 'max_retries': 0}]
    assert calls[0]['model'] == 'gpt-5-mini' and calls[0]['max_completion_tokens'] == 2000
    assert 'max_tokens' not in calls[0] and 'temperature' not in calls[0] and 'extra_body' not in calls[0]
    assert calls[0]['response_format'] == {'type': 'json_object'}
    assert result.model_id == 'openai:gpt-5-mini' and result.provider == 'openai' and result.structured_output_enforced
    assert result.input_tokens == 10 and result.cost_usd is None    # unverified price: nothing is estimated


def test_anthropic_models_omit_temperature_and_response_format_and_say_so():
    calls = []
    settings = Settings(anthropic_api_key='anthropic-private-key', faultlab_actor_model='anthropic:claude-sonnet-5-5')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=lambda **_: _client(calls, content='{"ok": true}'))
    result = asyncio.run(provider.complete([{'role': 'user', 'content': 'hi'}], response_contract='actor_final_report'))
    assert set(calls[0]) == {'model', 'messages', 'stream', 'timeout', 'max_tokens'}
    assert calls[0]['model'] == 'claude-sonnet-5-5' and calls[0]['max_tokens'] == 2000
    assert result.provider == 'anthropic' and result.structured_output_enforced is False
    assert result.model_id == 'anthropic:claude-sonnet-5-5' and result.content == '{"ok": true}'


def test_each_provider_gets_one_client_with_its_own_credentials():
    calls, factories = [], []
    def factory(**kwargs):
        factories.append(kwargs)
        return _client(calls)
    settings = Settings(wandb_api_key='wandb-private-key', wandb_entity='team', wandb_project='proj',
                        wandb_model='deepseek-ai/DeepSeek-V3.1', openrouter_api_key='router-private-key',
                        faultlab_explorer_model='openrouter:anthropic/claude-sonnet-5-5',
                        faultlab_mechanic_model='openrouter:openai/gpt-4.1')
    async def run():
        async with RuntimeProvider(settings, live_authorized=True, client_factory=factory) as provider:
            return [await provider.complete([{'role': 'user', 'content': 'x'}], role=role)
                    for role in ('actor', 'explorer', 'mechanic', 'actor')]
    generations = asyncio.run(run())
    assert [generation.provider for generation in generations] == ['wandb', 'openrouter', 'openrouter', 'wandb']
    assert [spec['base_url'] for spec in factories] == ['https://api.inference.wandb.ai/v1', 'https://openrouter.ai/api/v1']
    assert factories[0]['api_key'] == 'wandb-private-key' and factories[0]['project'] == 'team/proj'
    assert factories[1]['api_key'] == 'router-private-key' and factories[1]['default_headers']['X-Title'] == 'FaultLab'
    assert [call['model'] for call in calls] == ['deepseek-ai/DeepSeek-V3.1', 'anthropic/claude-sonnet-5-5', 'openai/gpt-4.1',
                                                 'deepseek-ai/DeepSeek-V3.1']
    assert calls[0]['temperature'] == 0 and 'temperature' not in calls[1] and calls[2]['temperature'] == 0
    assert [generation.model_id for generation in generations] == [
        'deepseek-ai/DeepSeek-V3.1', 'openrouter:anthropic/claude-sonnet-5-5', 'openrouter:openai/gpt-4.1', 'deepseek-ai/DeepSeek-V3.1']


def test_openrouter_reported_cost_is_the_measured_cost():
    calls = []
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=10, cost=0.00123)
    settings = Settings(openrouter_api_key='router-private-key', faultlab_actor_model='openrouter:deepseek/deepseek-chat')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=lambda **_: _client(calls, usage=usage))
    result = asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert result.cost_usd == pytest.approx(0.00123) and result.input_tokens == 100 and result.output_tokens == 10


def _priced_openai_settings(tmp_path, **overrides):
    from datetime import date
    table = tmp_path / 'pricing.json'
    table.write_text(json.dumps({'schema': 'faultlab-pricing-table/v1', 'entries': [
        {'ref': 'openai:gpt-5-mini', 'input_per_million': 0.25, 'output_per_million': 2.0, 'verified': True,
         'verified_on': date.today().isoformat(), 'source': 'test'}]}))
    return Settings(openai_api_key='openai-private-key', faultlab_actor_model='openai:gpt-5-mini',
                    faultlab_pricing_table=str(table), **overrides)


def test_monthly_cap_refuses_before_the_client_once_reserved_bounds_reach_it(tmp_path):
    from app.providers.spend import SpendLedger
    calls = []
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100)
    settings = _priced_openai_settings(tmp_path, faultlab_monthly_dollar_cap=0.02)
    assert settings.per_call_dollar_bound_for_role('actor') == pytest.approx(0.012)    # 32,000 in + 2,000 out per million
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=lambda **_: _client(calls, usage=usage),
                               spend_ledger=ledger)
    first = asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert first.cost_usd == pytest.approx(0.00045)    # 1,000 in + 100 out at the verified rates
    with pytest.raises(RuntimeProviderError) as refused:
        asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert refused.value.code == 'MONTHLY_CAP' and len(calls) == 1
    assert 'private-key' not in str(refused.value)
    summary = ledger.summary()
    assert summary.calls == 1 and summary.reserved_bound == pytest.approx(0.012)
    assert summary.settled_actual == pytest.approx(0.00045)


def test_a_failed_priced_call_keeps_its_reserved_bound(tmp_path):
    from app.providers.spend import SpendLedger
    async def create(**kwargs):
        raise RuntimeError('provider exploded')
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    provider = RuntimeProvider(_priced_openai_settings(tmp_path), live_authorized=True, spend_ledger=ledger,
                               client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(RuntimeProviderError) as failed:
        asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert failed.value.code == 'PROVIDER_ERROR'
    summary = ledger.summary()
    assert summary.calls == 1 and summary.reserved_bound == pytest.approx(0.012) and summary.settled_actual is None


def test_unpriced_models_reserve_nothing_and_cost_nothing_known(tmp_path):
    from app.providers.spend import SpendLedger
    calls = []
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    settings = Settings(openai_api_key='openai-private-key', faultlab_actor_model='openai:gpt-4.1', faultlab_monthly_dollar_cap=0.000001)
    provider = RuntimeProvider(settings, live_authorized=True, spend_ledger=ledger,
                               client_factory=lambda **_: _client(calls, usage=SimpleNamespace(prompt_tokens=5, completion_tokens=1)))
    result = asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert result.cost_usd is None and ledger.summary().calls == 0 and len(calls) == 1


def test_every_provider_credential_is_redacted_and_refused_as_input():
    calls = []
    settings = Settings(openai_api_key='openai-private-key', anthropic_api_key='anthropic-private-key',
                        faultlab_custom_api_key='custom-private-key', faultlab_actor_model='openai:gpt-4.1')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=lambda **_: _client(
        calls, content='echo anthropic-private-key, openai-private-key and custom-private-key'))
    result = asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    assert result.content == 'echo [redacted], [redacted] and [redacted]'
    with pytest.raises(RuntimeProviderError) as error:
        asyncio.run(provider.complete([{'role': 'user', 'content': 'see custom-private-key'}]))
    assert error.value.code == 'SECRET_INPUT' and len(calls) == 1


def test_missing_provider_credentials_are_named_before_any_client():
    from app.config import ConfigurationError
    settings = Settings(faultlab_actor_model='anthropic:claude-sonnet-5-5')
    provider = RuntimeProvider(settings, live_authorized=True, client_factory=lambda **_: pytest.fail('Client before credentials'))
    with pytest.raises(ConfigurationError, match='^ANTHROPIC_API_KEY$'):
        asyncio.run(provider.complete([{'role': 'user', 'content': 'x'}]))
    custom = Settings(faultlab_actor_model='custom:local-model')
    with pytest.raises(ConfigurationError, match='^FAULTLAB_CUSTOM_BASE_URL, FAULTLAB_CUSTOM_API_KEY$'):
        asyncio.run(RuntimeProvider(custom, live_authorized=True, client_factory=lambda **_: pytest.fail('x')).complete(
            [{'role': 'user', 'content': 'x'}]))


def test_frozen_settings_keep_wandb_identity_and_describe_other_providers():
    from pathlib import Path
    from app.providers.runtime import MODEL_REQUEST_SETTINGS, model_request_settings
    assert model_request_settings('deepseek-ai/DeepSeek-V3.1') == MODEL_REQUEST_SETTINGS
    assert model_request_settings('') == MODEL_REQUEST_SETTINGS and model_request_settings(None) == MODEL_REQUEST_SETTINGS
    assert model_request_settings('openai:gpt-5-mini') == {**MODEL_REQUEST_SETTINGS, 'provider': 'openai',
        'token_limit_parameter': 'max_completion_tokens', 'temperature': None, 'response_format_enforced': True}
    assert model_request_settings('openai:gpt-4.1')['temperature'] == 0
    assert model_request_settings('anthropic:claude-sonnet-5-5') == {**MODEL_REQUEST_SETTINGS, 'provider': 'anthropic',
        'token_limit_parameter': 'max_tokens', 'temperature': None, 'response_format_enforced': False}
    # A campaign exported before other providers existed still carries exactly today's settings for its model.
    export = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/diagnosis-rules/exports/v2g.json').read_text())
    configuration = export['configuration']
    assert configuration['model_settings'] == model_request_settings(configuration['model'])
    assert all(configuration['model_settings_by_role'][role] == model_request_settings(model)
               for role, model in configuration['models'].items())
