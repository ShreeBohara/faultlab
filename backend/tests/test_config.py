"""Exercise configuration with temporary files, never the real root .env."""

from dataclasses import fields
from pathlib import Path

import pytest

from app import config
from app.config import ConfigurationError, Settings


@pytest.fixture(autouse=True)
def clear_provider_environment(monkeypatch):
    for setting in fields(Settings):
        monkeypatch.delenv(setting.name.upper(), raising=False)


def test_missing_configuration_reports_only_names(tmp_path):
    settings = Settings.from_env(env_path=tmp_path / "missing.env")

    with pytest.raises(ConfigurationError) as error:
        settings.require_wandb()

    assert error.value.missing_fields == ("WANDB_API_KEY", "WANDB_ENTITY", "WANDB_PROJECT")
    assert str(error.value) == "WANDB_API_KEY, WANDB_ENTITY, WANDB_PROJECT"


def test_environment_overrides_file_and_blank_override_is_respected(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WANDB_API_KEY=file-secret\nWANDB_ENTITY=file-entity\n"
        "WANDB_PROJECT=file-project\nWANDB_MODEL=file-model\n"
        "TYPESAFE_API_KEY=typesafe-secret\nTYPESAFE_BASE_URL=https://example.invalid\n"
        "TYPESAFE_MODEL=typesafe-model\n"
    )
    monkeypatch.setenv("WANDB_API_KEY", "environment-secret")
    monkeypatch.setenv("WANDB_MODEL", "")

    settings = Settings.from_env(env_path=env_file)

    assert settings.wandb_api_key == "environment-secret"
    assert settings.project_path == "file-entity/file-project"
    assert settings.wandb_model == ""
    assert settings.typesafe_api_key == "typesafe-secret"
    assert settings.typesafe_base_url == "https://example.invalid"
    assert settings.typesafe_model == "typesafe-model"
    settings.require_wandb()
    with pytest.raises(ConfigurationError, match="^WANDB_MODEL$"):
        settings.require_wandb(require_model=True)
    assert "WANDB_ENTITY" not in config.os.environ


def test_secrets_are_excluded_from_repr():
    settings = Settings(wandb_api_key="wandb-secret", typesafe_api_key="typesafe-secret")

    assert "wandb-secret" not in repr(settings)
    assert "typesafe-secret" not in repr(settings)


def test_fully_configured_wandb_can_require_model():
    settings = Settings(
        wandb_api_key="dummy-key", wandb_entity="test-team",
        wandb_project="test-project", wandb_model="configured-model",
    )

    assert settings.require_wandb(require_model=True) is None
    assert settings.project_path == "test-team/test-project"


def test_default_env_path_is_explicit_repository_root(monkeypatch):
    calls = []

    def fake_dotenv_values(*, dotenv_path, interpolate):
        calls.append((dotenv_path, interpolate))
        return {}

    monkeypatch.setattr(config, "dotenv_values", fake_dotenv_values)
    Settings.from_env()

    expected_path = Path(config.__file__).resolve().parents[2] / ".env"
    assert calls == [(expected_path, False)]


def test_dotenv_values_are_not_interpolated(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("WANDB_API_KEY=literal-${OTHER_VALUE}\n")
    monkeypatch.setenv("OTHER_VALUE", "expanded-value")

    settings = Settings.from_env(env_path=env_file)

    assert settings.wandb_api_key == "literal-${OTHER_VALUE}"


def test_local_capability_survives_restart_without_env_edits(tmp_path):
    settings = Settings(faultlab_artifact_dir=str(tmp_path))
    token = settings.local_control_token()
    assert len(token) >= 32
    assert settings.local_control_token() == token
    assert (tmp_path / 'control-capability').stat().st_mode & 0o077 == 0
    assert not (tmp_path / '.env').exists()


def test_live_defaults_deny_dispatch():
    settings = Settings(wandb_api_key='fixture',wandb_entity='team',wandb_project='p',wandb_model='m')
    with pytest.raises(ConfigurationError):settings.require_live()


def test_concurrent_local_capability_creation_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    settings = Settings(faultlab_artifact_dir=str(tmp_path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: settings.local_control_token(), range(8)))
    assert len(set(values)) == 1


def test_live_campaign_requires_priced_bound_for_exact_model():
    from dataclasses import replace
    settings=Settings(wandb_api_key='fixture',wandb_entity='team',wandb_project='p',wandb_model='m',faultlab_live_enabled=True,faultlab_confirmed_entity='team')
    assert settings.model_call_dollar_bound is None
    with pytest.raises(ConfigurationError):settings.require_live()
    priced=replace(settings,faultlab_input_dollars_per_million=1.0,faultlab_output_dollars_per_million=2.0,faultlab_pricing_model='m',faultlab_pricing_verified=True)
    priced.require_live()
    assert priced.model_call_dollar_bound==.036
    assert replace(priced,wandb_model='different').model_call_dollar_bound is None
    with pytest.raises(ConfigurationError):replace(priced,faultlab_input_dollars_per_million=float('nan')).require_live()


def test_expanded_token_cap_keeps_call_and_dollar_caps():
    from dataclasses import replace
    from app.contracts.models import CampaignBudget
    from app.providers.runtime import MODEL_REQUEST_SETTINGS
    settings=Settings(wandb_api_key='fixture',wandb_entity='team',wandb_project='p',wandb_model='deepseek-ai/DeepSeek-V3.1',
        faultlab_live_enabled=True,faultlab_confirmed_entity='team',faultlab_pricing_model='deepseek-ai/DeepSeek-V3.1',
        faultlab_input_dollars_per_million=.55,faultlab_output_dollars_per_million=1.65,faultlab_pricing_verified=True)
    settings.require_live()
    assert settings.faultlab_token_cap==CampaignBudget().tokens==204000000
    assert settings.faultlab_model_call_cap==6000 and settings.faultlab_dollar_cap==100
    assert settings.model_call_dollar_bound==pytest.approx(.0209)
    assert MODEL_REQUEST_SETTINGS['max_input_tokens']==CampaignBudget().input_tokens_per_call==32000
    with pytest.raises(ConfigurationError):replace(settings,faultlab_token_cap=204000001).require_live()


def test_split_role_models_have_frozen_verified_price_bounds():
    from app.contracts.models import CampaignBudget
    from app.lab.configuration import frozen_configuration
    settings=Settings(
        wandb_api_key='fixture',wandb_entity='team',wandb_project='p',
        wandb_model='meta-llama/Llama-3.1-8B-Instruct',
        wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813',
        wandb_mechanic_model='deepseek-ai/DeepSeek-V4-Pro-0813',
        faultlab_live_enabled=True,faultlab_confirmed_entity='team',
        faultlab_input_dollars_per_million=.22,faultlab_output_dollars_per_million=.22,
        faultlab_pricing_model='meta-llama/Llama-3.1-8B-Instruct',faultlab_pricing_verified=True,
        faultlab_reasoning_input_dollars_per_million=1.31,faultlab_reasoning_output_dollars_per_million=3.96,
        faultlab_reasoning_pricing_model='deepseek-ai/DeepSeek-V4-Pro-0813',faultlab_reasoning_pricing_verified=True)
    settings.require_live()
    assert settings.model_call_dollar_bounds==pytest.approx(
        {'actor':.00748,'explorer':.04984,'mechanic':.04984})
    frozen=frozen_configuration(settings,CampaignBudget(),'live-v1')
    assert frozen['model']==settings.wandb_model
    assert frozen['models']==settings.role_models
    assert frozen['pricing']['actor']['model']==settings.wandb_model
    assert frozen['pricing']['explorer']['per_call_dollar_upper_bound']==pytest.approx(.04984)
