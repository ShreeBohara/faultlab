"""Explicit server-side configuration; importing this module performs no I/O."""

from dataclasses import dataclass, field, fields
import os
from pathlib import Path

from dotenv import dotenv_values


ROOT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class ConfigurationError(ValueError):
    """Identify missing configuration by name, without exposing values."""

    def __init__(self, missing_fields: tuple[str, ...]) -> None:
        self.missing_fields = missing_fields
        super().__init__(", ".join(missing_fields))


@dataclass(frozen=True)
class Settings:
    wandb_api_key: str = field(default="", repr=False)
    wandb_entity: str = ""
    wandb_project: str = ""
    wandb_model: str = ""
    typesafe_api_key: str = field(default="", repr=False)
    typesafe_base_url: str = ""
    typesafe_model: str = ""

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "Settings":
        """Read the explicit root .env, then apply process environment overrides.

        Pass a temporary path in tests to avoid loading local credentials. Values
        are not interpolated or copied into the process environment.
        """
        file_values = dotenv_values(
            dotenv_path=ROOT_ENV_PATH if env_path is None else env_path,
            interpolate=False,
        )
        values = {}
        for setting in fields(cls):
            name = setting.name.upper()
            value = os.environ.get(name, file_values.get(name))
            values[setting.name] = (value or "").strip()
        return cls(**values)

    def require_wandb(self, require_model: bool = False) -> None:
        """Validate only when a caller explicitly requests a provider check."""
        required = ["wandb_api_key", "wandb_entity", "wandb_project"]
        if require_model:
            required.append("wandb_model")
        missing = tuple(name.upper() for name in required if not getattr(self, name).strip())
        if missing:
            raise ConfigurationError(missing)

    @property
    def project_path(self) -> str:
        return f"{self.wandb_entity}/{self.wandb_project}"
