"""Build-reviewed local registrations; request data never chooses Python code."""
from __future__ import annotations

from hashlib import sha256
from importlib import metadata
from pathlib import Path
import re

from app.contracts.models import AgentRegistration, EpisodeBudget, content_hash, canonical_json
from app.providers.runtime import model_request_settings

ROOT = Path(__file__).resolve().parents[3]
REVISION = "12c1bc820eca50ace6f80a21d90426d41d74f845"
NATIVE_FILES = {
    "agents.py": "da0da2e258c346e28d97b3584dfe58dcd203fc20fbde6c6533e333f9b1a06352",
    "models.py": "e3510666f0a36d1d09d25d9d9f2e9cb0e0c09edc47ed599b0e52445bddf146e7",
    "prompts/toolcalling_agent.yaml": "28820f24906dd3ee3faa8160945e00529dda2a39c9fa8b3362093c0560c4b8f7",
}
HOOKS = ["after_upgrade_response", "before_confirmation", "after_notification_response", "before_final_report"]


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def adapter_hash():
    return content_hash({name: digest(Path(__file__).with_name(name)) for name in ("registry.py", "external_agent.py")})


def verify_native_source():
    distribution = metadata.distribution("smolagents")
    if distribution.version != "1.26.0":
        raise ValueError("Reviewed smolagents version is 1.26.0")
    directory = Path(distribution.locate_file("smolagents"))
    for name, expected in NATIVE_FILES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("Reviewed native source digest mismatch")
    authored_files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in installed native source rejected")
        if path.is_file() and path.suffix in (".py", ".yaml", ".yml"):
            authored_files[path.relative_to(directory).as_posix()] = digest(path)
    return content_hash({"revision": REVISION, "files": authored_files})


def native_prompt_hash():
    from app.integrations.external_agent import TASK_CONTRACT, TRANSPORT_CONTRACT
    return content_hash({"native_template": NATIVE_FILES["prompts/toolcalling_agent.yaml"], "task_contract": TASK_CONTRACT, "transport": TRANSPORT_CONTRACT})


def _configuration(configuration):
    required = {"model", "actor_prompt_hash", "adapter_hash", "source_hash", "contract_hash", "service_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash", "episode_budget", "model_settings"}
    if not isinstance(configuration, dict) or not required <= set(configuration):
        raise ValueError("Complete independently frozen target configuration required")
    allowed = required | {"schema_version", "models", "model_settings_by_role", "pricing", "campaign_budget", "profile_id", "external_source_revision", "external_agent_version", "lab_model", "lab_model_settings", "lab_pricing"}
    if set(configuration) - allowed or not isinstance(configuration["model"], str) or "://" in configuration["model"] or not isinstance(configuration.get("lab_model", ""), str):
        raise ValueError("Unreviewed target configuration fields or service URL")
    def no_location(value):
        if isinstance(value, dict):
            return all(no_location(item) for item in value.values())
        if isinstance(value, list):
            return all(no_location(item) for item in value)
        return not isinstance(value, str) or ("://" not in value and not value.startswith(("/", "\\")))
    if not no_location(configuration):
        raise ValueError("Service URLs and filesystem paths are not configuration capabilities")
    for key in required - {"model", "episode_budget", "model_settings"}:
        if not isinstance(configuration[key], str) or not re.fullmatch("[a-f0-9]{64}", configuration[key]):
            raise ValueError("Invalid frozen configuration digest")
    if configuration["episode_budget"] != EpisodeBudget().model_dump(mode="json"):
        raise ValueError("Target does not support the reviewed episode budget")
    if configuration["model_settings"] != model_request_settings(configuration["model"]):
        raise ValueError("Target model settings are unsupported")
    models=configuration.get("models")
    settings_by_role=configuration.get("model_settings_by_role")
    if models is not None:
        if set(models)!={"actor","explorer","mechanic"} or models["actor"]!=configuration["model"]:
            raise ValueError("Frozen role models are invalid")
        if not isinstance(settings_by_role,dict) or set(settings_by_role)!=set(models):
            raise ValueError("Frozen role model settings are incomplete")
        if any(settings_by_role[role]!=model_request_settings(model) for role,model in models.items()):
            raise ValueError("Frozen role model settings are unsupported")
    return configuration


def _installed_semantics(configuration):
    # Compute identities from installed reviewed code. A source bundle and a
    # matching attacker-supplied target cannot attest to their own semantics.
    from app.config import Settings
    from app.contracts.models import CampaignBudget
    from app.lab.configuration import frozen_configuration
    actual = frozen_configuration(Settings(), CampaignBudget(), "offline-v1")
    for field in ("contract_hash", "service_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash"):
        if configuration.get(field) != actual[field]:
            raise ValueError("Target shared semantics or dependency lock differ from the installed reviewed runtime")


def freeze_target_configuration(source_configuration, model_id):
    """Keep shared semantics, independently freeze the target's native identity."""
    source = _configuration(source_configuration)
    _installed_semantics(source)
    if not model_id or len(model_id) > 600:
        raise ValueError("Explicit target model required")
    target = {**source, "model": model_id, "source_hash": verify_native_source(),
        "adapter_hash": adapter_hash(), "actor_prompt_hash": native_prompt_hash(),
        "external_source_revision": REVISION, "external_agent_version": "smolagents/1.26.0"}
    if "models" in target:
        target["models"]={**target["models"],"actor":model_id}
        target["model_settings_by_role"]={**target["model_settings_by_role"],"actor":model_request_settings(model_id)}
    target["model_settings"]=model_request_settings(model_id)
    return target


class AgentRegistry:
    def __init__(self, store):
        self.store = store

    def list(self):
        return [AgentRegistration.model_validate_json(canonical_json(row)) for row in self.store.list_records("agent_registrations")]

    def get(self, registration_id):
        raw = self.store.get_record("agent_registrations", registration_id)
        if raw is None:
            raise ValueError("Unsupported locally reviewed registration ID")
        return AgentRegistration.model_validate_json(canonical_json(raw))

    def register_smolagents(self, configuration):
        target = _configuration(configuration)
        _installed_semantics(target)
        source_hash = verify_native_source()
        if target["source_hash"] != source_hash or target["adapter_hash"] != adapter_hash() or target["actor_prompt_hash"] != native_prompt_hash():
            raise ValueError("Target configuration is not the reviewed native adapter")
        config_hash = content_hash(target)
        registration = AgentRegistration(
            registration_id="smolagents-1.26.0-" + config_hash[:16], name="Hugging Face smolagents ToolCallingAgent", version="1.26.0",
            provenance_class="external", source_origin="https://github.com/huggingface/smolagents", source_owner="Hugging Face and smolagents contributors",
            source_revision=REVISION, source_hash=source_hash, license="Apache-2.0", permission_ref="Apache-2.0 public source; reviewed pinned release",
            adapter_entrypoint_id="smolagents-toolcalling-v1", adapter_hash=adapter_hash(), contract_hash=target["contract_hash"], capability_hash=target["capability_hash"],
            reset_profile_id="fresh-orders-v1", oracle_hash=target["scorer_hash"], policy_hooks=HOOKS,
            model=target["model"], prompt_hash=target["actor_prompt_hash"], configuration_hash=config_hash,
            dependency_lock_hash=target["dependency_lock_hash"], budget_compatible=True, dry_run_status="PASSED",
            limitations=["Dry-run conformance covers reviewed source and local contract mappings; provider access and external outcome measurements remain pending.", "Only ToolCallingAgent and four synthetic order tools are supported.", "Native reasoning and prompt template are preserved; a typed text transport maps one model-selected tool per turn."])
        self._save(registration, target)
        return registration

    def register_reference(self, configuration, *, internal_smoke=False):
        target = _configuration(configuration)
        _installed_semantics(target)
        from app.lab.configuration import tree_hash
        from app.agents.actor import ACTOR_PROMPT_HASH
        if target["source_hash"] != tree_hash(ROOT / "backend/app/agents") or target["adapter_hash"] != tree_hash(ROOT / "backend/app/adapters") or target["actor_prompt_hash"] != ACTOR_PROMPT_HASH:
            raise ValueError("Reference source configuration mismatch")
        config_hash = content_hash(target)
        registration = AgentRegistration(registration_id=("internal-smoke-" if internal_smoke else "orders-v1-") + config_hash[:16],
            name="FaultLab reference actor", version="1.0.0", provenance_class="internal_smoke" if internal_smoke else "reference",
            source_origin="local:FaultLab", source_owner="FaultLab project", source_revision="faultlab-v1", source_hash=target["source_hash"],
            license="Local project source", permission_ref="User-authorized local implementation", adapter_entrypoint_id="orders-prototype-v1",
            adapter_hash=target["adapter_hash"], contract_hash=target["contract_hash"], capability_hash=target["capability_hash"], reset_profile_id="fresh-orders-v1",
            oracle_hash=target["scorer_hash"], policy_hooks=HOOKS, model=target["model"], prompt_hash=target["actor_prompt_hash"], configuration_hash=config_hash,
            dependency_lock_hash=target["dependency_lock_hash"], budget_compatible=True, dry_run_status="PASSED",
            limitations=["This reference/internal fixture is not independent external validation."])
        self._save(registration, target)
        return registration

    def _save(self, registration, configuration):
        self.store.put_record("configurations", registration.configuration_hash, configuration, immutable=True)
        self.store.put_record("agent_registrations", registration.registration_id, registration, immutable=True)

    def verify(self, registration_id, target_configuration):
        registration = self.get(registration_id)
        target = _configuration(target_configuration)
        _installed_semantics(target)
        if content_hash(target) != registration.configuration_hash:
            raise ValueError("Target differs from its independently frozen registration")
        if registration.dry_run_status != "PASSED" or not registration.budget_compatible or registration.reset_profile_id != "fresh-orders-v1" or set(registration.policy_hooks) != set(HOOKS):
            raise ValueError("Unsupported reset, policy hooks or budget")
        pairs = {"contract_hash": "contract_hash", "capability_hash": "capability_hash", "oracle_hash": "scorer_hash", "adapter_hash": "adapter_hash", "source_hash": "source_hash", "prompt_hash": "actor_prompt_hash", "dependency_lock_hash": "dependency_lock_hash", "model": "model"}
        if any(getattr(registration, field) != target[key] for field, key in pairs.items()):
            raise ValueError("Registration/configuration identity mismatch")
        if registration.adapter_entrypoint_id == "smolagents-toolcalling-v1":
            if registration.provenance_class != "external" or registration.source_hash != verify_native_source() or registration.adapter_hash != adapter_hash() or registration.prompt_hash != native_prompt_hash():
                raise ValueError("Reviewed external source or adapter has changed")
        elif registration.adapter_entrypoint_id == "orders-prototype-v1":
            from app.lab.configuration import tree_hash
            from app.agents.actor import ACTOR_PROMPT_HASH
            if registration.provenance_class == "external" or target["source_hash"] != tree_hash(ROOT / "backend/app/agents") or target["adapter_hash"] != tree_hash(ROOT / "backend/app/adapters") or target["actor_prompt_hash"] != ACTOR_PROMPT_HASH:
                raise ValueError("Reference registration integrity mismatch")
        else:
            raise ValueError("Unreviewed adapter entrypoint")
        return registration

    def reviewed_actor(self, registration_id, provider=None, model_id=None):
        registration = self.get(registration_id)
        configuration = self.store.get_record("configurations", registration.configuration_hash)
        self.verify(registration_id, configuration)
        if model_id is not None and model_id != registration.model:
            raise ValueError("Requested model differs from registration")
        if registration.adapter_entrypoint_id == "smolagents-toolcalling-v1":
            from app.integrations.external_agent import SmolagentsActor
            return SmolagentsActor(model_id=registration.model)
        from app.agents.actor import Actor
        return Actor()
