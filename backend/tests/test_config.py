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
