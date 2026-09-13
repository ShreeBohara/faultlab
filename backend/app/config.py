"""Explicit server-side configuration; importing this module performs no I/O."""

from dataclasses import dataclass, field, fields, MISSING
import os
from pathlib import Path

from dotenv import dotenv_values
from app.contracts.models import CampaignBudget, CAMPAIGN_TOKEN_LIMIT


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
    wandb_explorer_model: str = ""
    wandb_mechanic_model: str = ""
    typesafe_api_key: str = field(default="", repr=False)
    typesafe_base_url: str = ""
    typesafe_model: str = ""

    faultlab_artifact_dir: str = 'artifacts'
    faultlab_simulator_url: str = 'http://127.0.0.1:8001'
    faultlab_control_token: str = field(default='', repr=False)
    faultlab_live_enabled: bool = False
    faultlab_confirmed_entity: str = ''
    faultlab_model_call_cap: int = 6000
    faultlab_token_cap: int = CAMPAIGN_TOKEN_LIMIT
    faultlab_dollar_cap: float = 100.0
    # Negative rates mean unverified. Explicit short provider checks use
    # require_wandb(); campaign admission additionally requires a priced bound.
    faultlab_input_dollars_per_million: float = -1.0
    faultlab_output_dollars_per_million: float = -1.0
    faultlab_pricing_model: str = ''
    faultlab_pricing_verified: bool = False
    faultlab_lab_model: str = ''
    faultlab_lab_input_dollars_per_million: float = -1.0
    faultlab_lab_output_dollars_per_million: float = -1.0
    faultlab_lab_pricing_model: str = ''
    faultlab_reasoning_input_dollars_per_million: float = -1.0
    faultlab_reasoning_output_dollars_per_million: float = -1.0
    faultlab_reasoning_pricing_model: str = ''
    faultlab_reasoning_pricing_verified: bool = False

    def model_for(self, role: str) -> str:
        if role == "explorer":
            if self.wandb_explorer_model.strip():
                return self.wandb_explorer_model.strip()
            if self.faultlab_lab_model.strip():
                return self.faultlab_lab_model.strip()
        elif role == "mechanic":
            if self.wandb_mechanic_model.strip():
                return self.wandb_mechanic_model.strip()
            if self.faultlab_lab_model.strip():
                return self.faultlab_lab_model.strip()
        return self.wandb_model

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
            if value is None:
                values[setting.name] = setting.default if setting.default is not MISSING else ''
            elif setting.type is bool:
                if value.strip().lower() not in ('true','false','1','0',''):
                    raise ConfigurationError((name,))
                values[setting.name] = value.strip().lower() in ('true','1')
            elif setting.type in (int, float):
                try:
                    values[setting.name] = setting.type(value)
                except (ValueError, TypeError):
                    raise ConfigurationError((name,)) from None
            else:
                values[setting.name] = (value or '').strip()
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

    def model_for_role(self, role: str) -> str:
        if role not in ("actor", "explorer", "mechanic"):
            raise ValueError("Unknown model role")
        return self.model_for(role)

    @property
    def role_models(self) -> dict[str, str]:
        return {role: self.model_for_role(role) for role in ("actor", "explorer", "mechanic")}

    def require_live(self) -> None:
        self.require_wandb(require_model=True)
        missing = []
        if not self.faultlab_live_enabled:
            missing.append('FAULTLAB_LIVE_ENABLED')
        if self.faultlab_confirmed_entity != self.wandb_entity:
            missing.append('FAULTLAB_CONFIRMED_ENTITY')
        if not (1 <= self.faultlab_model_call_cap <= 6000):
            missing.append('FAULTLAB_MODEL_CALL_CAP')
        if not (1 <= self.faultlab_token_cap <= CAMPAIGN_TOKEN_LIMIT):
            missing.append('FAULTLAB_TOKEN_CAP')
        if not (0 < self.faultlab_dollar_cap <= 500):
            missing.append('FAULTLAB_DOLLAR_CAP')
        import math
        for name in ('faultlab_input_dollars_per_million','faultlab_output_dollars_per_million'):
            value=getattr(self,name)
            if not math.isfinite(value) or value<0: missing.append(name.upper())
        if self.faultlab_pricing_model!=self.wandb_model:
            missing.append('FAULTLAB_PRICING_MODEL')
        if not self.faultlab_pricing_verified:
            missing.append('FAULTLAB_PRICING_VERIFIED')
        if self.faultlab_lab_model.strip():
            for name in ('faultlab_lab_input_dollars_per_million','faultlab_lab_output_dollars_per_million'):
                value=getattr(self,name)
                if not math.isfinite(value) or value<0: missing.append(name.upper())
            if self.faultlab_lab_pricing_model!=self.faultlab_lab_model.strip():
                missing.append('FAULTLAB_LAB_PRICING_MODEL')
        explicit={self.wandb_explorer_model.strip(), self.wandb_mechanic_model.strip()} - {'', self.wandb_model}
        if explicit:
            for name in ('faultlab_reasoning_input_dollars_per_million','faultlab_reasoning_output_dollars_per_million'):
                value=getattr(self,name)
                if not math.isfinite(value) or value<0: missing.append(name.upper())
            if len(explicit)!=1 or self.faultlab_reasoning_pricing_model not in explicit:
                missing.append('FAULTLAB_REASONING_PRICING_MODEL')
            if not self.faultlab_reasoning_pricing_verified:
                missing.append('FAULTLAB_REASONING_PRICING_VERIFIED')
        if missing:
            raise ConfigurationError(tuple(dict.fromkeys(missing)))

    @property
    def model_call_dollar_bounds(self) -> dict[str, float] | None:
        import math
        caps=CampaignBudget()
        actor_rates=(self.faultlab_input_dollars_per_million,self.faultlab_output_dollars_per_million)
        if (not self.faultlab_pricing_verified or self.faultlab_pricing_model!=self.wandb_model
                or any(not math.isfinite(v) or v<0 for v in actor_rates)):
            return None
        actor_bound=(caps.input_tokens_per_call*actor_rates[0]+caps.output_tokens_per_call*actor_rates[1])/1000000
        result={'actor':actor_bound}
        reasoning_rates=(self.faultlab_reasoning_input_dollars_per_million,self.faultlab_reasoning_output_dollars_per_million)
        lab_rates=(self.faultlab_lab_input_dollars_per_million,self.faultlab_lab_output_dollars_per_million)
        for role in ('explorer','mechanic'):
            model=self.model_for_role(role)
            if model==self.wandb_model:
                result[role]=actor_bound
            elif (self.faultlab_reasoning_pricing_verified and self.faultlab_reasoning_pricing_model==model
                    and all(math.isfinite(v) and v>=0 for v in reasoning_rates)):
                result[role]=(caps.input_tokens_per_call*reasoning_rates[0]+caps.output_tokens_per_call*reasoning_rates[1])/1000000
            elif (self.faultlab_lab_model.strip()==model and self.faultlab_lab_pricing_model==model
                    and all(math.isfinite(v) and v>=0 for v in lab_rates)):
                result[role]=(caps.input_tokens_per_call*lab_rates[0]+caps.output_tokens_per_call*lab_rates[1])/1000000
            else:
                return None
        return result

    @property
    def model_call_dollar_bound(self) -> float | None:
        """Worst-case dollars per admitted call across every configured role model."""
        bounds=self.model_call_dollar_bounds
        return max(bounds.values()) if bounds else None

    @property
    def artifact_path(self) -> Path:
        value = Path(self.faultlab_artifact_dir)
        return value if value.is_absolute() else ROOT_ENV_PATH.parent / value

    def local_control_token(self) -> str:
        """Share an opaque localhost-only capability without modifying the real .env.

        Called only by explicitly constructed simulator/coordinator services. File
        permissions and exclusive creation prevent accidental replacement on restart.
        """
        if self.faultlab_control_token:
            return self.faultlab_control_token
        import secrets
        path = self.artifact_path / 'control-capability'
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = path.parent / ('.control-' + secrets.token_hex(12))
        descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        token = secrets.token_urlsafe(32)
        try:
            with os.fdopen(descriptor, 'w') as file:
                file.write(token)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(candidate, path)
            except FileExistsError:
                if path.is_symlink():
                    raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',))
                token = path.read_text().strip()
                if len(token) < 32:
                    raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',))
            return token
        finally:
            candidate.unlink(missing_ok=True)
