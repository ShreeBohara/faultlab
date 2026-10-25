"""Explicit server-side configuration; importing this module performs no I/O."""

from dataclasses import dataclass, field, fields, MISSING
import os
from pathlib import Path

from dotenv import dotenv_values
from app.contracts.models import CampaignBudget, CAMPAIGN_TOKEN_LIMIT


ROOT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_ROLE_MODELS = {
    'wandb_model': 'deepseek-ai/DeepSeek-V3.1',
    'wandb_explorer_model': 'deepseek-ai/DeepSeek-V4-Pro-0813',
    'wandb_mechanic_model': 'deepseek-ai/DeepSeek-V4-Pro-0813',
}


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
    faultlab_read_only: bool = False
    faultlab_simulator_url: str = 'http://127.0.0.1:8001'
    faultlab_control_token: str = field(default='', repr=False)
    faultlab_live_enabled: bool = False
    faultlab_actor_context_protocol: str = 'faultlab-actor-context/v4-indexed-evidence'
    # Allows an explicitly bounded Inference/Weave-only experiment without
    # publishing a Finished W&B run that would trigger additional Aria spending.
    faultlab_aria_publish_enabled: bool = False
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

    # Providers beyond W&B. A model is a reference "provider:model_id"; an unprefixed name
    # belongs to FAULTLAB_DEFAULT_PROVIDER, so every older configuration keeps its meaning.
    openai_api_key: str = field(default='', repr=False)
    anthropic_api_key: str = field(default='', repr=False)
    # Required by Anthropic for an organization-scoped key (one not tied to a workspace); blank otherwise.
    anthropic_workspace_id: str = ''
    openrouter_api_key: str = field(default='', repr=False)
    faultlab_custom_base_url: str = ''
    faultlab_custom_api_key: str = field(default='', repr=False)
    # The Claude Code CLI for the subscription channel (docs/providers.md); a name on PATH or a path.
    faultlab_claude_code_bin: str = 'claude'
    faultlab_default_provider: str = 'wandb'
    # Generic role models take precedence over the WANDB_* names when set.
    faultlab_actor_model: str = ''
    faultlab_explorer_model: str = ''
    faultlab_mechanic_model: str = ''
    # Every admitted call reserves its worst-case bound against this calendar-month cap.
    faultlab_monthly_dollar_cap: float = 100.0
    faultlab_pricing_table: str = ''
    # The machine-wide monthly spend ledger; blank means ~/.faultlab/spend-ledger.sqlite3, shared by every store.
    faultlab_spend_ledger: str = ''
    faultlab_allow_stale_prices: bool = False
    # Weave tracing and verified evidence export; legacy Learn campaigns require it. False (plan item 1.11):
    # a live campaign starts no Weave worker, tracer or publisher; local evidence is the authority.
    faultlab_weave_enabled: bool = True
    # Whether a completion or baseline study must read each trial's evidence back from Weave (weave_verified)
    # or may take the local bundle (local_only). The study record carries the choice as evidence_requirement.
    faultlab_require_remote_evidence: bool = True

    def model_for(self, role: str) -> str:
        """The canonical model name for a role: a bare W&B id, or ``provider:model`` for any other provider.

        FAULTLAB_<ROLE>_MODEL wins; then the legacy WANDB_* and FAULTLAB_LAB_MODEL selections. An
        unprefixed name belongs to FAULTLAB_DEFAULT_PROVIDER, and the name is recorded in its canonical
        spelling (app.providers.catalog.canonical_model_name), so frozen configurations never depend on
        the writing machine's default provider.
        """
        explicit = {'actor': self.faultlab_actor_model, 'explorer': self.faultlab_explorer_model,
                    'mechanic': self.faultlab_mechanic_model}.get(role, '').strip()
        if explicit:
            return self._canonical_model_name(explicit)
        if role == "explorer":
            if self.wandb_explorer_model.strip():
                return self._canonical_model_name(self.wandb_explorer_model)
            if self.faultlab_lab_model.strip():
                return self._canonical_model_name(self.faultlab_lab_model)
        elif role == "mechanic":
            if self.wandb_mechanic_model.strip():
                return self._canonical_model_name(self.wandb_mechanic_model)
            if self.faultlab_lab_model.strip():
                return self._canonical_model_name(self.faultlab_lab_model)
        return self._canonical_model_name(self.faultlab_actor_model.strip() or self.wandb_model)

    def _canonical_model_name(self, name: str) -> str:
        from app.providers.catalog import canonical_model_name
        return canonical_model_name(name, self.faultlab_default_provider)

    def _blank_model_names(self) -> tuple[str, ...]:
        """Which settings name a role's model when every selection is blank."""
        return ('WANDB_MODEL',) if self.faultlab_default_provider == 'wandb' else ('FAULTLAB_ACTOR_MODEL',)

    def model_ref_for_role(self, role: str):
        """The provider and bare model id behind a role's canonical model name."""
        from app.providers.catalog import parse_model_ref
        model = self.model_for_role(role)
        if not model:
            raise ConfigurationError(self._blank_model_names())
        return parse_model_ref(model)

    def providers_in_use(self) -> tuple[str, ...]:
        """Every provider some role's model lives on, in role order, without repeats."""
        from app.providers.catalog import parse_model_ref
        providers = [parse_model_ref(model).provider for model in self.role_models.values() if model]
        return tuple(dict.fromkeys(providers))

    def require_provider(self, role: str) -> None:
        """Refuse a role whose model is blank or whose provider lacks credentials; names only, never values."""
        from app.providers.catalog import client_spec
        spec = client_spec(self.model_ref_for_role(role), self)
        if spec.missing:
            raise ConfigurationError(spec.missing)

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
            # Old .env templates shipped empty model placeholders. Adopt the
            # tested defaults for those placeholders without modifying the file.
            # An explicitly blank process override still disables that selection.
            if setting.name in DEFAULT_ROLE_MODELS and name not in os.environ and not value:
                value = None
            if value is None:
                # Application startup uses the tested role split. Explicit values,
                # including blank process overrides and the legacy shared lab model, win.
                legacy_lab = os.environ.get('FAULTLAB_LAB_MODEL', file_values.get('FAULTLAB_LAB_MODEL'))
                default_model = DEFAULT_ROLE_MODELS.get(setting.name)
                if setting.name in ('wandb_explorer_model', 'wandb_mechanic_model') and legacy_lab:
                    default_model = ''
                values[setting.name] = default_model if default_model is not None else (
                    setting.default if setting.default is not MISSING else '')
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
        from app.agents.progress import ACTOR_CONTEXT_PROTOCOLS
        if values['faultlab_actor_context_protocol'] not in ACTOR_CONTEXT_PROTOCOLS:
            raise ConfigurationError(('FAULTLAB_ACTOR_CONTEXT_PROTOCOL',))
        from app.providers.catalog import PROVIDER_IDS
        if values['faultlab_default_provider'] not in PROVIDER_IDS:
            raise ConfigurationError(('FAULTLAB_DEFAULT_PROVIDER',))
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
        """Refuse paid work unless every role has credentials, a verified price and declared caps."""
        import math
        from app.providers.catalog import UnknownProviderError, client_spec
        missing = []
        if not self.faultlab_live_enabled:
            missing.append('FAULTLAB_LIVE_ENABLED')
        if self.faultlab_read_only:
            missing.append('FAULTLAB_READ_ONLY')
        if not (1 <= self.faultlab_model_call_cap <= 6000):
            missing.append('FAULTLAB_MODEL_CALL_CAP')
        if not (1 <= self.faultlab_token_cap <= CAMPAIGN_TOKEN_LIMIT):
            missing.append('FAULTLAB_TOKEN_CAP')
        if not (0 < self.faultlab_dollar_cap <= 500):
            missing.append('FAULTLAB_DOLLAR_CAP')
        if not (math.isfinite(self.faultlab_monthly_dollar_cap) and self.faultlab_monthly_dollar_cap > 0):
            missing.append('FAULTLAB_MONTHLY_DOLLAR_CAP')
        uses_wandb = False
        for role in ('actor', 'explorer', 'mechanic'):
            try:
                ref = self.model_ref_for_role(role)
            except UnknownProviderError:
                missing.append('FAULTLAB_DEFAULT_PROVIDER')
                continue
            except ConfigurationError as error:
                missing.extend(error.missing_fields)
                continue
            uses_wandb = uses_wandb or ref.provider == 'wandb'
            missing.extend(client_spec(ref, self).missing)
            if self.model_rates_for_role(role) is None:
                # Not a setting: a verified, dated entry for this model in the pricing table (docs/providers.md).
                missing.append(f'PRICING:{ref.ref}')
        if uses_wandb or self.faultlab_weave_enabled:
            # Weave evidence is credited to the confirmed W&B entity, exactly like W&B Inference itself.
            missing.extend(name.upper() for name in ('wandb_api_key', 'wandb_entity', 'wandb_project')
                           if not getattr(self, name).strip())
            if not self.wandb_entity.strip() or self.faultlab_confirmed_entity != self.wandb_entity:
                missing.append('FAULTLAB_CONFIRMED_ENTITY')
        if missing:
            raise ConfigurationError(tuple(dict.fromkeys(missing)))

    def model_rates_for_role(self, role: str) -> tuple[float, float] | None:
        """Use one verified model/rate selection for admission and frozen records.

        Explicit FAULTLAB_*_DOLLARS_PER_MILLION settings win; otherwise the dated pricing
        table supplies verified, fresh rates for the role's provider:model reference.
        """
        from app.providers.pricing import PricingTableError, table_rates
        try:
            explicit = self._explicit_rates_for_role(role)
            if explicit is not None:
                return explicit
            ref = self.model_ref_for_role(role)
            table = Path(self.faultlab_pricing_table) if self.faultlab_pricing_table else None
            if ref.provider == 'claude-code':
                # Shadow pricing: a subscription call costs no money, but it is bounded, capped and recorded at the
                # API price of the same model so holds, caps and read-outs keep their meaning (docs/providers.md).
                return table_rates(f'anthropic:{ref.model_id}', path=table, allow_stale=self.faultlab_allow_stale_prices)
            return table_rates(ref.ref, path=table, allow_stale=self.faultlab_allow_stale_prices)
        except (PricingTableError, ValueError):
            # UnknownProviderError and ConfigurationError are ValueErrors: an unpriceable role has no bound.
            return None

    def _explicit_rates_for_role(self, role: str) -> tuple[float, float] | None:
        """The FAULTLAB_*_DOLLARS_PER_MILLION selections of earlier campaigns, matched by canonical name."""
        import math
        model=self.model_for_role(role)
        canonical=self._canonical_model_name
        actor_rates=(self.faultlab_input_dollars_per_million,self.faultlab_output_dollars_per_million)
        if model==canonical(self.wandb_model):
            return actor_rates if (self.faultlab_pricing_verified and canonical(self.faultlab_pricing_model)==model
                and all(math.isfinite(v) and v>=0 for v in actor_rates)) else None
        reasoning_rates=(self.faultlab_reasoning_input_dollars_per_million,self.faultlab_reasoning_output_dollars_per_million)
        lab_rates=(self.faultlab_lab_input_dollars_per_million,self.faultlab_lab_output_dollars_per_million)
        if (self.faultlab_reasoning_pricing_verified and canonical(self.faultlab_reasoning_pricing_model)==model
                and all(math.isfinite(v) and v>=0 for v in reasoning_rates)):
            return reasoning_rates
        if (canonical(self.faultlab_lab_model)==model and canonical(self.faultlab_lab_pricing_model)==model
                and all(math.isfinite(v) and v>=0 for v in lab_rates)):
            return lab_rates
        return None

    def per_call_dollar_bound_for_role(self, role: str) -> float | None:
        """Worst-case dollars for one admitted call of this role, from its verified rates."""
        rates = self.model_rates_for_role(role)
        if rates is None:
            return None
        caps = CampaignBudget()
        return (caps.input_tokens_per_call * rates[0] + caps.output_tokens_per_call * rates[1]) / 1000000

    @property
    def spend_ledger_path(self) -> Path:
        """One ledger per machine, not per store: the monthly cap must see every run."""
        if self.faultlab_spend_ledger.strip():
            return Path(self.faultlab_spend_ledger).expanduser()
        return Path.home() / '.faultlab' / 'spend-ledger.sqlite3'

    @property
    def model_call_dollar_bounds(self) -> dict[str, float] | None:
        caps=CampaignBudget()
        rates={role:self.model_rates_for_role(role) for role in ('actor','explorer','mechanic')}
        if any(value is None for value in rates.values()):
            return None
        return {role:(caps.input_tokens_per_call*value[0]+caps.output_tokens_per_call*value[1])/1000000
                for role,value in rates.items()}

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
        An existing capability file is used only if it is a regular file (not a symlink)
        owned by the current user with no group or other permission bits (for example
        0600); anything else is refused, naming FAULTLAB_CONTROL_TOKEN.
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
                token = _read_private_capability(path)
                if len(token) < 32:
                    raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',))
            return token
        finally:
            candidate.unlink(missing_ok=True)


def _read_private_capability(path: Path) -> str:
    """Read an existing control capability only if no other local user could have planted or read it."""
    import stat
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',)) from None
    # Check the opened object before wrapping it: a directory opens on some systems, and
    # fdopen would then raise a raw IsADirectoryError and leave the descriptor open.
    try:
        info = os.fstat(descriptor)
        foreign_owner = hasattr(os, 'getuid') and info.st_uid != os.getuid()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or foreign_owner:
            raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',))
        file = os.fdopen(descriptor, 'r')
    except BaseException as error:
        os.close(descriptor)
        if isinstance(error, (ConfigurationError, OSError)):
            raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',)) from None
        raise
    with file:
        try:
            return file.read().strip()
        except (OSError, UnicodeDecodeError):
            raise ConfigurationError(('FAULTLAB_CONTROL_TOKEN',)) from None
