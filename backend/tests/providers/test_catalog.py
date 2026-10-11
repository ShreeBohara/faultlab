"""Model references, request profiles and client specs; no client is ever created here."""
import pytest

from app.config import Settings
from app.providers import catalog, wandb_inference
from app.providers.catalog import (ModelRef, UnknownProviderError, canonical_model_name, client_spec, parse_model_ref,
                                   provider_secrets, request_profile)

JSON = {'type': 'json_object'}


@pytest.mark.parametrize('name,default,expected', [
    ('deepseek-ai/DeepSeek-V3.1', 'wandb', ('wandb', 'deepseek-ai/DeepSeek-V3.1')),
    ('openai:gpt-5-mini', 'wandb', ('openai', 'gpt-5-mini')),
    ('anthropic:claude-sonnet-5-5', 'wandb', ('anthropic', 'claude-sonnet-5-5')),
    ('openrouter:qwen/qwen3-235b:free', 'wandb', ('openrouter', 'qwen/qwen3-235b:free')),
    ('custom:llama-local', 'wandb', ('custom', 'llama-local')),
    ('gpt-5-mini', 'openai', ('openai', 'gpt-5-mini')),
    ('meta-llama/Llama:tagged', 'wandb', ('wandb', 'meta-llama/Llama:tagged')),
    ('  wandb:deepseek-ai/DeepSeek-V3.1 ', 'openai', ('wandb', 'deepseek-ai/DeepSeek-V3.1')),
])
def test_model_references_split_only_on_known_provider_prefixes(name, default, expected):
    ref = parse_model_ref(name, default)
    assert (ref.provider, ref.model_id) == expected and ref.ref == f'{expected[0]}:{expected[1]}'


@pytest.mark.parametrize('name,default', [('', 'wandb'), ('   ', 'wandb'), (None, 'wandb'), ('model', 'bogus'), ('openai:', 'bogus')])
def test_blank_names_and_unknown_default_providers_are_refused(name, default):
    with pytest.raises(UnknownProviderError):
        parse_model_ref(name, default)


@pytest.mark.parametrize('name,default,expected', [
    ('deepseek-ai/DeepSeek-V3.1', 'wandb', 'deepseek-ai/DeepSeek-V3.1'),
    ('wandb:deepseek-ai/DeepSeek-V3.1', 'openai', 'deepseek-ai/DeepSeek-V3.1'),
    ('gpt-5-mini', 'openai', 'openai:gpt-5-mini'),
    ('openai:gpt-5-mini', 'wandb', 'openai:gpt-5-mini'),
    ('', 'openai', ''),
    ('   ', 'wandb', ''),
])
def test_canonical_names_spell_out_every_provider_but_wandb(name, default, expected):
    assert canonical_model_name(name, default) == expected


def test_wandb_profile_sends_exactly_the_historical_request():
    assert catalog.WANDB_BASE_URL == wandb_inference.BASE_URL
    thinking = request_profile(ModelRef('wandb', 'deepseek-ai/DeepSeek-V4-Pro-0813'))
    assert thinking.request_kwargs(max_output_tokens=2000, response_format=JSON) == {
        'max_tokens': 2000, 'temperature': 0, 'response_format': JSON,
        'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}
    plain = request_profile(ModelRef('wandb', 'deepseek-ai/DeepSeek-V3.1'))
    assert plain.request_kwargs(max_output_tokens=5, response_format=JSON) == {
        'max_tokens': 5, 'temperature': 0, 'response_format': JSON}
    assert plain.frozen() == {'provider': 'wandb', 'token_limit_parameter': 'max_tokens', 'temperature': 0,
                              'response_format_enforced': True}


@pytest.mark.parametrize('model,temperature', [('gpt-5', None), ('gpt-5-mini', None), ('gpt-5.5', None), ('o3-mini', None),
                                               ('gpt-5-chat-latest', 0), ('gpt-4.1', 0)])
def test_openai_profile_uses_max_completion_tokens_and_omits_temperature_for_reasoning_models(model, temperature):
    kwargs = request_profile(ModelRef('openai', model)).request_kwargs(max_output_tokens=7, response_format=JSON)
    assert kwargs['max_completion_tokens'] == 7 and 'max_tokens' not in kwargs
    assert kwargs.get('temperature') == temperature and ('temperature' in kwargs) == (temperature is not None)
    assert kwargs['response_format'] == JSON


def test_anthropic_profile_sends_neither_temperature_nor_response_format():
    profile = request_profile(ModelRef('anthropic', 'claude-sonnet-5-5'))
    assert profile.request_kwargs(max_output_tokens=9, response_format=JSON) == {'max_tokens': 9}
    assert profile.response_format_enforced is False and profile.temperature is None


@pytest.mark.parametrize('model,temperature', [('anthropic/claude-sonnet-5-5', None), ('openai/gpt-5-mini', None),
                                               ('openai/gpt-4.1', 0), ('deepseek/deepseek-chat', 0), ('qwen/qwen3:free', 0)])
def test_openrouter_profile_applies_vendor_rules_by_prefix(model, temperature):
    kwargs = request_profile(ModelRef('openrouter', model)).request_kwargs(max_output_tokens=3, response_format=JSON)
    assert kwargs['max_tokens'] == 3 and kwargs['response_format'] == JSON
    assert kwargs.get('temperature') == temperature and ('temperature' in kwargs) == (temperature is not None)


def test_custom_profile_is_the_plain_openai_compatible_request():
    assert request_profile(ModelRef('custom', 'anything')).request_kwargs(max_output_tokens=1, response_format=JSON) == {
        'max_tokens': 1, 'temperature': 0, 'response_format': JSON}


def test_unknown_provider_has_no_profile_and_no_client():
    with pytest.raises(UnknownProviderError):
        request_profile(ModelRef('bogus', 'm'))
    with pytest.raises(UnknownProviderError):
        client_spec(ModelRef('bogus', 'm'), Settings())


def test_client_specs_name_missing_settings_without_values():
    blank = Settings()
    expected = {'wandb': ('WANDB_API_KEY', 'WANDB_ENTITY', 'WANDB_PROJECT'), 'openai': ('OPENAI_API_KEY',),
                'anthropic': ('ANTHROPIC_API_KEY',), 'openrouter': ('OPENROUTER_API_KEY',),
                'custom': ('FAULTLAB_CUSTOM_BASE_URL', 'FAULTLAB_CUSTOM_API_KEY')}
    for provider, names in expected.items():
        spec = client_spec(ModelRef(provider, 'm'), blank)
        assert spec.missing == names and not spec.configured
    assert provider_secrets(blank) == ()


def test_configured_client_specs_carry_each_providers_base_url_and_options():
    settings = Settings(wandb_api_key='w-key', wandb_entity='team', wandb_project='proj', openai_api_key='o-key',
                        anthropic_api_key='a-key', openrouter_api_key='r-key',
                        faultlab_custom_base_url=' http://127.0.0.1:11434/v1 ', faultlab_custom_api_key='c-key')
    wandb = client_spec(ModelRef('wandb', 'm'), settings)
    assert wandb.configured and wandb.base_url == catalog.WANDB_BASE_URL and wandb.api_key == 'w-key'
    assert wandb.client_kwargs == {'project': 'team/proj'}
    openai = client_spec(ModelRef('openai', 'm'), settings)
    assert openai.base_url == catalog.OPENAI_BASE_URL and openai.api_key == 'o-key' and openai.client_kwargs == {}
    anthropic = client_spec(ModelRef('anthropic', 'm'), settings)
    assert anthropic.base_url == catalog.ANTHROPIC_BASE_URL and anthropic.api_key == 'a-key' and anthropic.client_kwargs == {}
    scoped = client_spec(ModelRef('anthropic', 'm'), Settings(anthropic_api_key='a-key', anthropic_workspace_id=' wrkspc_123 '))
    assert scoped.client_kwargs == {'default_headers': {'anthropic-workspace-id': 'wrkspc_123'}} and scoped.configured
    openrouter = client_spec(ModelRef('openrouter', 'm'), settings)
    assert openrouter.base_url == catalog.OPENROUTER_BASE_URL and openrouter.api_key == 'r-key'
    assert openrouter.client_kwargs == {'default_headers': {'HTTP-Referer': 'https://github.com/ShreeBohara/faultlab',
                                                            'X-Title': 'FaultLab'}}
    custom = client_spec(ModelRef('custom', 'm'), settings)
    assert custom.base_url == 'http://127.0.0.1:11434/v1' and custom.api_key == 'c-key' and custom.configured
    assert 'c-key' not in repr(custom) and 'c-key' not in str(custom)
    assert provider_secrets(settings) == ('w-key', 'o-key', 'a-key', 'r-key', 'c-key')
    assert 'o-key' not in repr(settings) and 'a-key' not in repr(settings) and 'r-key' not in repr(settings)
    assert 'c-key' not in repr(settings)


@pytest.mark.parametrize('url,usable', [
    ('https://gateway.example.com/v1', True), ('http://localhost:8000/v1', True), ('http://127.0.0.1:11434/v1', True),
    ('http://[::1]:8000/v1', True), ('http://gateway.example.com/v1', False), ('ftp://example.com', False),
    ('gateway.example.com/v1', False), ('https://', False),
])
def test_custom_endpoints_receive_the_key_only_over_tls_or_loopback(url, usable):
    spec = client_spec(ModelRef('custom', 'm'), Settings(faultlab_custom_base_url=url, faultlab_custom_api_key='c-key'))
    assert spec.configured is usable
    if not usable:
        assert spec.missing == ('FAULTLAB_CUSTOM_BASE_URL',)
