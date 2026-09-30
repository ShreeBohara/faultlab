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
REFERENCE_ENTRYPOINT = "orders-prototype-v1"
# Two declared native adapters for the same unmodified smolagents agent. v1 is the default wherever a
# default exists; v2 (app.integrations.external_agent_v2) is chosen explicitly. They are separate agents:
# the entry point is part of every identity, so their registrations, plans and histories never merge.
NATIVE_V1 = "smolagents-toolcalling-v1"
NATIVE_V2 = "smolagents-toolcalling-v2"
NATIVE_ENTRYPOINTS = (NATIVE_V1, NATIVE_V2)
# Saved-plan and API agent kinds, and the reviewed entry point each selects.
AGENT_ENTRYPOINTS = {"reference": REFERENCE_ENTRYPOINT, "smolagents": NATIVE_V1, "smolagents-v2": NATIVE_V2}
ENTRYPOINT_AGENTS = {entry: agent for agent, entry in AGENT_ENTRYPOINTS.items()}
NATIVE_AGENTS = ("smolagents", "smolagents-v2")
NATIVE_V2_DISPLAY_NAME = "smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)"
_ADAPTER_FILES = {NATIVE_V1: ("registry.py", "external_agent.py"),
                  NATIVE_V2: ("registry.py", "external_agent.py", "external_agent_v2.py")}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _native_entrypoint(entrypoint):
    if entrypoint not in NATIVE_ENTRYPOINTS:
        raise ValueError("Unreviewed adapter entrypoint")
    return entrypoint


def adapter_hash(entrypoint=NATIVE_V1):
    """v1: registry.py + external_agent.py, as before. v2 also covers its own module and the evidence-label code
    it executes (app/agents/progress.py); v2 imports and runs v1's module, so that file is covered too."""
    files = {name: digest(Path(__file__).with_name(name)) for name in _ADAPTER_FILES[_native_entrypoint(entrypoint)]}
    if entrypoint == NATIVE_V2:
        files["agents/progress.py"] = digest(Path(__file__).parents[1] / "agents" / "progress.py")
    return content_hash(files)


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


def native_prompt_hash(entrypoint=NATIVE_V1):
    from app.integrations.external_agent import TASK_CONTRACT, TRANSPORT_CONTRACT
    identity = {"native_template": NATIVE_FILES["prompts/toolcalling_agent.yaml"], "task_contract": TASK_CONTRACT, "transport": TRANSPORT_CONTRACT}
    if _native_entrypoint(entrypoint) == NATIVE_V2:
        # v2 sends v1's task contract and transport text, plus its declared labels and final-turn protocol
        # (including the final-turn tool text and the structured-output contract's hashes).
        from app.integrations.external_agent_v2 import adapter_protocol
        identity["adapter_protocol"] = adapter_protocol()
    return content_hash(identity)


def _configuration(configuration):
    required = {"model", "actor_prompt_hash", "adapter_hash", "source_hash", "contract_hash", "service_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash", "episode_budget", "model_settings"}
    if not isinstance(configuration, dict) or not required <= set(configuration):
        raise ValueError("Complete independently frozen target configuration required")
    allowed = required | {"schema_version", "models", "model_settings_by_role", "pricing", "campaign_budget", "profile_id", "external_source_revision", "external_agent_version", "lab_model", "lab_model_settings", "lab_pricing", "algorithm_hash", "runtime_hash", "trace_contract_version", "actor_response_protocol", "actor_context_protocols", "actor_context_protocol"}
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
    # Historical configurations remain readable; new identities must be complete.
    provenance_fields = {"algorithm_hash", "runtime_hash", "trace_contract_version"}
    if provenance_fields & configuration.keys():
        if not provenance_fields <= configuration.keys() or configuration["trace_contract_version"] != 2:
            raise ValueError("Incomplete or unsupported runtime identity")
        if any(not isinstance(configuration[key], str) or not re.fullmatch("[a-f0-9]{64}", configuration[key]) for key in ("algorithm_hash", "runtime_hash")):
            raise ValueError("Invalid frozen runtime digest")
    if configuration["episode_budget"] != EpisodeBudget().model_dump(mode="json"):
        raise ValueError("Target does not support the reviewed episode budget")
    if configuration["model_settings"] != model_request_settings(configuration["model"]):
        raise ValueError("Target model settings are unsupported")
    if "actor_response_protocol" in configuration:
        from app.providers.runtime import actor_response_protocol
        if configuration["actor_response_protocol"] != actor_response_protocol():
            raise ValueError("Target actor response protocol is unsupported")
    if "actor_context_protocols" in configuration:
        from app.agents.progress import actor_context_protocols
        if configuration["actor_context_protocols"] != actor_context_protocols():
            raise ValueError("Target actor context protocols are unsupported")
    if "actor_context_protocol" in configuration:
        from app.agents.progress import ACTOR_CONTEXT_PROTOCOLS
        if configuration["actor_context_protocol"] not in ACTOR_CONTEXT_PROTOCOLS:
            raise ValueError("Target selected actor context protocol is unsupported")
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
    fields = ("contract_hash", "service_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash")
    fields += tuple(field for field in ("algorithm_hash", "runtime_hash", "trace_contract_version") if field in configuration)
    if "actor_response_protocol" in configuration:
        fields += ("actor_response_protocol",)
    if "actor_context_protocols" in configuration:
        fields += ("actor_context_protocols",)
    for field in fields:
        if configuration.get(field) != actual[field]:
            raise ValueError("Target shared semantics or dependency lock differ from the installed reviewed runtime")


def freeze_target_configuration(source_configuration, model_id, entrypoint=NATIVE_V1):
    """Keep shared semantics, independently freeze the target's native identity (v1 unless v2 is chosen)."""
    _native_entrypoint(entrypoint)
    source = _configuration(source_configuration)
    _installed_semantics(source)
    if not model_id or len(model_id) > 600:
        raise ValueError("Explicit target model required")
    target = {**source, "model": model_id, "source_hash": verify_native_source(),
        "adapter_hash": adapter_hash(entrypoint), "actor_prompt_hash": native_prompt_hash(entrypoint),
        "external_source_revision": REVISION, "external_agent_version": "smolagents/1.26.0"}
    # These protocols belong to the reference Actor's request builder. The
    # native adapter keeps its own reviewed prompt, memory and text transport.
    # Historical configurations remain readable; new identities state only the
    # protocols that their selected implementation actually executes.
    for field in ("actor_response_protocol", "actor_context_protocols", "actor_context_protocol"):
        target.pop(field, None)
    if "models" in target:
        target["models"]={**target["models"],"actor":model_id}
        target["model_settings_by_role"]={**target["model_settings_by_role"],"actor":model_request_settings(model_id)}
    target["model_settings"]=model_request_settings(model_id)
    return target


def current_registration_configuration(settings, caps, profile, registration):
    """Derive current configured semantics for a reviewed implementation."""
    from app.lab.configuration import frozen_configuration
    current = frozen_configuration(settings, caps, profile)
    if registration.adapter_entrypoint_id in NATIVE_ENTRYPOINTS:
        if profile != "live-v1":
            raise ValueError("Native agent execution requires the live configuration profile")
        return freeze_target_configuration(current, current["model"], registration.adapter_entrypoint_id)
    if registration.adapter_entrypoint_id != REFERENCE_ENTRYPOINT:
        raise ValueError("Unreviewed adapter entrypoint")
    return current


def reviewed_actor_matches(actor, registration):
    """Check an explicit in-process override against the reviewed factory."""
    if registration.adapter_entrypoint_id == NATIVE_V1:
        from app.integrations.external_agent import SmolagentsActor
        return type(actor) is SmolagentsActor and actor.model_id == registration.model
    if registration.adapter_entrypoint_id == NATIVE_V2:
        from app.integrations.external_agent_v2 import SmolagentsActorV2
        return type(actor) is SmolagentsActorV2 and actor.model_id == registration.model
    from app.adapters.prototype import run_prototype
    return actor is run_prototype and registration.adapter_entrypoint_id == "orders-prototype-v1"


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

    def register_smolagents(self, configuration, entrypoint=NATIVE_V1):
        """Register native adapter v1 (the default) or, when chosen explicitly, adapter v2."""
        _native_entrypoint(entrypoint)
        target = _configuration(configuration)
        _installed_semantics(target)
        source_hash = verify_native_source()
        if target["source_hash"] != source_hash or target["adapter_hash"] != adapter_hash(entrypoint) or target["actor_prompt_hash"] != native_prompt_hash(entrypoint):
            raise ValueError("Target configuration is not the reviewed native adapter")
        config_hash = content_hash(target)
        limitations = ["Registration checks reviewed installed source and local contract mappings only; it performs no provider-access check or behavior measurement.", "Only ToolCallingAgent and four synthetic order tools are supported.", "Native reasoning and prompt template are preserved; a typed text transport maps one model-selected tool per turn."]
        registration_id, name = "smolagents-1.26.0-" + config_hash[:16], "Hugging Face smolagents ToolCallingAgent"
        if entrypoint == NATIVE_V2:
            registration_id, name = "smolagents-1.26.0-adapter-v2-" + config_hash[:16], "Hugging Face " + NATIVE_V2_DISPLAY_NAME
            limitations += ["Adapter v2 shows each delivered observation's evidence_id as its journal label (obs-1, obs-2, ...) and decodes cited labels back to the real IDs before validation; an unknown token passes through unchanged.",
                            "Adapter v2 offers only final_answer on the final turn and asks the provider for structured output of the native final_answer action; an invalid output is not repaired.",
                            "Adapter v1 and adapter v2 are separate agents: their results, histories and policies are never pooled."]
        registration = AgentRegistration(
            registration_id=registration_id, name=name, version="1.26.0",
            provenance_class="external", source_origin="https://github.com/huggingface/smolagents", source_owner="Hugging Face and smolagents contributors",
            source_revision=REVISION, source_hash=source_hash, license="Apache-2.0", permission_ref="Apache-2.0 public source; reviewed pinned release",
            adapter_entrypoint_id=entrypoint, adapter_hash=adapter_hash(entrypoint), contract_hash=target["contract_hash"], capability_hash=target["capability_hash"],
            reset_profile_id="fresh-orders-v1", oracle_hash=target["scorer_hash"], policy_hooks=HOOKS,
            model=target["model"], prompt_hash=target["actor_prompt_hash"], configuration_hash=config_hash,
            dependency_lock_hash=target["dependency_lock_hash"], budget_compatible=True, dry_run_status="PASSED",
            limitations=limitations)
        self._save(registration, target)
        return registration

    def register_reference(self, configuration, *, internal_smoke=False):
        target = _configuration(configuration)
        _installed_semantics(target)
        from app.providers.runtime import actor_response_protocol
        if target.get("actor_response_protocol") != actor_response_protocol():
            raise ValueError("Reference actor response protocol must be explicitly frozen")
        from app.agents.progress import actor_context_protocols
        if target.get("actor_context_protocols") != actor_context_protocols():
            raise ValueError("Reference actor context protocols must be explicitly frozen")
        from app.lab.configuration import tree_hash
        from app.agents.actor import ACTOR_PROMPT_HASH
        if target["source_hash"] != tree_hash(ROOT / "backend/app/agents") or target["adapter_hash"] != tree_hash(ROOT / "backend/app/adapters") or target["actor_prompt_hash"] != ACTOR_PROMPT_HASH:
            raise ValueError("Reference source configuration mismatch")
        config_hash = content_hash(target)
        registration = AgentRegistration(registration_id=("internal-smoke-" if internal_smoke else "orders-v1-") + config_hash[:16],
            name="FaultLab reference actor", version="1.0.0", provenance_class="internal_smoke" if internal_smoke else "reference",
            source_origin="local:FaultLab", source_owner="FaultLab project", source_revision="faultlab-v1", source_hash=target["source_hash"],
            license="Local project source", permission_ref="User-authorized local implementation", adapter_entrypoint_id=REFERENCE_ENTRYPOINT,
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
        if registration.adapter_entrypoint_id in NATIVE_ENTRYPOINTS:
            entry = registration.adapter_entrypoint_id
            if registration.provenance_class != "external" or registration.source_hash != verify_native_source() or registration.adapter_hash != adapter_hash(entry) or registration.prompt_hash != native_prompt_hash(entry):
                raise ValueError("Reviewed external source or adapter has changed")
        elif registration.adapter_entrypoint_id == REFERENCE_ENTRYPOINT:
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
        if registration.adapter_entrypoint_id == NATIVE_V1:
            from app.integrations.external_agent import SmolagentsActor
            return SmolagentsActor(model_id=registration.model)
        if registration.adapter_entrypoint_id == NATIVE_V2:
            from app.integrations.external_agent_v2 import SmolagentsActorV2
            return SmolagentsActorV2(model_id=registration.model)
        # The registered reference executes the same tracked entrypoint as the
        # ordinary runner. Raw Actor bypasses the episode root/report trace.
        from app.adapters.prototype import run_prototype
        return run_prototype
