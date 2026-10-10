"""CLI-only native admission; saved data never selects executable Python.

Registration proves a reviewed bridge and pinned source, not successful behavior.
Every execution additionally requires the exact operator-supplied process binding
and its immutable campaign plan before EpisodeRunner can create a world.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re

from app.contracts.models import AgentRegistration, Campaign, CampaignBudget, canonical_json, content_hash, new_id
from app.lab.storage import StoreConflict
from app.native_agents.source import PROTOCOL, SourceSnapshot
from app.providers.runtime import model_request_settings

ENTRYPOINT = "smolagents-user-code-v1"
MODEL_ID = "faultlab-native-orders-double/v1"
PLAN_PROTOCOL = "faultlab-native-plan/v1"
CONFIG_FIELDS = {"native_agent_protocol", "native_candidate_source_hash", "native_framework_source_hash", "native_execution_identity_hash"}
MARKERS = ("native_plan_protocol", "native_plan_ref", "native_plan_hash")


def _digest(value):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value) is not None


def validate_configuration_marker(configuration):
    if not CONFIG_FIELDS.intersection(configuration):
        return
    if (not CONFIG_FIELDS.issubset(configuration) or configuration["native_agent_protocol"] != PROTOCOL
            or any(not _digest(configuration[key]) for key in CONFIG_FIELDS - {"native_agent_protocol"})):
        raise ValueError("Incomplete native configuration identity")


def adapter_hash():
    root = Path(__file__).parents[1]
    paths = list((root / "native_agents").glob("*.py"))
    paths += [root / name for name in ("integrations/registry.py", "lab/runner.py",
              "local_agents/source.py", "local_agents/transport.py", "integrations/external_agent.py",
              "integrations/external_agent_v2.py", "agents/progress.py")]
    return content_hash({path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
                         for path in sorted(paths)})


def _binding(provider):
    from app.native_agents.transport import NativeAgentProvider, _bridge_identity
    if type(provider) is not NativeAgentProvider or type(provider.snapshot) is not SourceSnapshot:
        raise ValueError("Explicit reviewed native process binding required")
    provider.snapshot.verify()
    expected = {**provider.snapshot.descriptor, **_bridge_identity(),
                "turn_timeout_seconds": provider.turn_timeout_seconds}
    if canonical_json(provider.identity) != canonical_json(expected):
        raise ValueError("Native process identity changed")
    return deepcopy(expected)


def _source_hash(identity):
    return content_hash({"protocol": PROTOCOL, "candidate_source_hash": identity["source_hash"],
                         "framework_source_hash": identity["framework_source_hash"]})


def _prompt_hash(identity):
    # The arbitrary constructor's realized prompt is retained by the worker.
    # This is its frozen construction identity, not a claim about model behavior.
    return content_hash({"constructor_source_hash": identity["source_hash"],
                         "bridge_hash": identity["bridge_hash"], "protocol": PROTOCOL})


def freeze_native_configuration(base_configuration, provider):
    from app.integrations.registry import _configuration, _installed_semantics, REVISION
    target = deepcopy(_configuration(base_configuration))
    _installed_semantics(target)
    identity = _binding(provider)
    for field in ("actor_response_protocol", "actor_context_protocols", "actor_context_protocol"):
        target.pop(field, None)
    target.update(model=MODEL_ID, model_settings=model_request_settings(MODEL_ID),
                  source_hash=_source_hash(identity), adapter_hash=adapter_hash(),
                  actor_prompt_hash=_prompt_hash(identity), external_source_revision=REVISION,
                  external_agent_version="smolagents/1.26.0", native_agent_protocol=PROTOCOL,
                  native_candidate_source_hash=identity["source_hash"],
                  native_framework_source_hash=identity["framework_source_hash"],
                  native_execution_identity_hash=content_hash(identity))
    if "models" in target:
        target["models"]["actor"] = MODEL_ID
        target["model_settings_by_role"]["actor"] = model_request_settings(MODEL_ID)
    _configuration(target)
    return target


def register_native(store, configuration, provider):
    from app.integrations.registry import AgentRegistry, HOOKS
    identity = _binding(provider)
    if canonical_json(configuration) != canonical_json(freeze_native_configuration(configuration, provider)):
        raise ValueError("Native configuration is not independently frozen")
    config_hash = content_hash(configuration)
    registration = AgentRegistration(
        registration_id="smolagents-user-code-v1-" + config_hash[:16],
        name="Operator-selected native smolagents constructor", version="1.0.0", provenance_class="external",
        source_origin="local:operator-selected-native-source", source_owner="Operator-selected source author",
        source_revision=identity["source_hash"], source_hash=configuration["source_hash"],
        license="Author-controlled local source", permission_ref="Explicit operator-selected trusted local file",
        adapter_entrypoint_id=ENTRYPOINT, adapter_hash=configuration["adapter_hash"],
        contract_hash=configuration["contract_hash"], capability_hash=configuration["capability_hash"],
        reset_profile_id="fresh-orders-v1", oracle_hash=configuration["scorer_hash"], policy_hooks=HOOKS,
        model=MODEL_ID, prompt_hash=configuration["actor_prompt_hash"], configuration_hash=config_hash,
        dependency_lock_hash=configuration["dependency_lock_hash"], budget_compatible=True, dry_run_status="PASSED",
        limitations=["Structural registration only; no successful behavior or provider access is established.",
                     "Native ToolCallingAgent runs authored construction with a deterministic offline model double.",
                     "Trusted local code with accident guards; not an operating-system security sandbox.",
                     "This candidate is distinct from reference and reviewed smolagents adapter v1/v2 identities."])
    with store.transaction():
        store.put_record("native_registration_identities", registration.registration_id, identity, immutable=True)
        AgentRegistry(store)._save(registration, configuration)
        AgentRegistry(store).verify(registration.registration_id, configuration)
    return registration


def verify_registration(store, registration, target):
    from app.native_agents.transport import _bridge_identity
    identity = store.get_record("native_registration_identities", registration.registration_id)
    validate_configuration_marker(target)
    if (not isinstance(identity, dict) or not CONFIG_FIELDS.issubset(target)
            or registration.provenance_class != "external" or target["model"] != MODEL_ID
            or target.get("profile_id") != "offline-v1"
            or not {"algorithm_hash", "runtime_hash", "trace_contract_version"}.issubset(target)
            or registration.registration_id != "smolagents-user-code-v1-" + content_hash(target)[:16]
            or target["native_execution_identity_hash"] != content_hash(identity)
            or target["native_candidate_source_hash"] != identity.get("source_hash")
            or target["native_framework_source_hash"] != identity.get("framework_source_hash")
            or identity.get("protocol") != PROTOCOL or identity.get("callback") != "build_agent"
            or target["source_hash"] != _source_hash(identity)
            or target["actor_prompt_hash"] != _prompt_hash(identity)
            or target["adapter_hash"] != adapter_hash()
            or any(field in target for field in ("actor_response_protocol", "actor_context_protocols", "actor_context_protocol"))):
        raise ValueError("Native registration identity mismatch")
    current = _bridge_identity()
    if canonical_json({key: identity.get(key) for key in current}) != canonical_json(current):
        raise ValueError("Native installed framework or bridge identity changed")


def reviewed_actor(store, registration, provider):
    from app.native_agents.actor import NativeActor
    identity = _binding(provider)
    saved = store.get_record("native_registration_identities", registration.registration_id)
    if canonical_json(identity) != canonical_json(saved):
        raise ValueError("Native candidate binding differs from registration")
    if not any(row.get("plan", {}).get("registration_id") == registration.registration_id
               and row.get("plan", {}).get("execution_identity_hash") == content_hash(identity)
               and row.get("plan_hash") == content_hash(row.get("plan"))
               for row in store.list_records("native_campaign_plans")):
        raise ValueError("Native actor requires its explicit saved execution plan")
    return NativeActor(provider)


def create_native_campaign(coordinator, request, provider, *, scenario_hash,
                           scenario_manifest_hash=None, required_trials, fixture_id="standard-v1"):
    from app.lab.configuration import frozen_configuration, source_provenance
    if (request.mode != "baseline" or request.config_profile_id != "offline-v1"
            or type(required_trials) is not int or required_trials not in (1, 3)
            or not _digest(scenario_hash) or fixture_id != "standard-v1"
            or (required_trials == 3 and not _digest(scenario_manifest_hash))
            or (required_trials == 1 and scenario_manifest_hash is not None)):
        raise ValueError("Native plans require an explicit baseline healthy check or three-trial imported regression")
    settings, store = coordinator.settings, coordinator.store
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap, tokens=settings.faultlab_token_cap,
                          dollars=float(settings.faultlab_dollar_cap))
    frozen = freeze_native_configuration(frozen_configuration(settings, caps, "offline-v1"), provider)
    policy = coordinator.policies.baseline()
    with store.transaction():
        registration = register_native(store, frozen, provider)
        campaign = Campaign(campaign_id=new_id("campaign"), **request.model_dump(), model=MODEL_ID,
                            configuration_hash=content_hash(frozen), caps=caps)
        plan = {"protocol": PLAN_PROTOCOL, "campaign_id": campaign.campaign_id,
                **request.model_dump(), "caps": caps.model_dump(mode="json"),
                "configuration_hash": campaign.configuration_hash, "registration_id": registration.registration_id,
                "execution_identity_hash": frozen["native_execution_identity_hash"],
                "candidate_source_hash": frozen["native_candidate_source_hash"],
                "source_mode": "offline_fixture", "arm": "B0", "policy_hash": policy.policy_hash,
                "policy_version": policy.version, "scenario_hash": scenario_hash,
                "scenario_manifest_hash": scenario_manifest_hash, "required_trials": required_trials,
                "fixture_id": fixture_id}
        plan_hash = content_hash(plan)
        coordinator.save(campaign)
        store.put_record("campaign_registrations", campaign.campaign_id,
                         {"registration_id": registration.registration_id}, immutable=True)
        store.put_record("native_campaign_plans", campaign.campaign_id,
                         {"plan": plan, "plan_hash": plan_hash}, immutable=True)
        store.put_record("campaign_provenance", campaign.campaign_id,
                         {**source_provenance(), "aria_publication_enabled": False,
                          "native_plan_protocol": PLAN_PROTOCOL, "native_plan_ref": campaign.campaign_id,
                          "native_plan_hash": plan_hash}, immutable=True)
        store.compare_and_set_pointer(f"active-policy:{campaign.campaign_id}", None, policy.version)
    return campaign


def has_native_marker(store, campaign, frozen, registration_id, actor=None, provider=None):
    provenance = store.get_record("campaign_provenance", campaign.campaign_id) or {}
    bound = store.get_record("campaign_registrations", campaign.campaign_id) or {}
    ids = (registration_id, bound.get("registration_id"))
    return bool(campaign.model == MODEL_ID or frozen.get("model") == MODEL_ID
                or CONFIG_FIELDS.intersection(frozen) or any(key in provenance for key in MARKERS)
                or store.get_record("native_campaign_plans", campaign.campaign_id) is not None
                or any(isinstance(value, str) and (value.startswith(ENTRYPOINT) or
                       (store.get_record("agent_registrations", value) or {}).get("adapter_entrypoint_id") == ENTRYPOINT)
                       for value in ids)
                or any(value is not None and type(value).__module__.startswith("app.native_agents.")
                       for value in (actor, provider)))


def resolve_native_execution(store, campaign, frozen, *, arm, purpose, study_id, source_mode,
                             registration_id, actor, actor_context_protocol, offline_fixture,
                             provider, recipe, policy, fixture_id, trial_index):
    from app.integrations.registry import AgentRegistry
    from app.native_agents.actor import NativeActor
    raw = store.get_record("native_campaign_plans", campaign.campaign_id) or {}
    plan = raw.get("plan")
    provenance = store.get_record("campaign_provenance", campaign.campaign_id) or {}
    bound = store.get_record("campaign_registrations", campaign.campaign_id) or {}
    if (not isinstance(plan, dict) or raw.get("plan_hash") != content_hash(plan)
            or plan.get("protocol") != PLAN_PROTOCOL or plan.get("campaign_id") != campaign.campaign_id
            or any(provenance.get(key) != value for key, value in zip(MARKERS, (PLAN_PROTOCOL, campaign.campaign_id, raw.get("plan_hash"))))
            or store.get_record("campaign_plans", campaign.campaign_id) is not None
            or any(key in provenance for key in ("run_plan_protocol", "run_plan_ref", "run_plan_hash"))):
        raise StoreConflict("Native execution requires its intact, separate immutable plan")
    if (not offline_fixture or source_mode != "offline_fixture" or actor_context_protocol is not None
            or arm != "B0" or plan.get("arm") != arm or campaign.mode != "baseline"
            or campaign.config_profile_id != "offline-v1" or campaign.model != MODEL_ID
            or any(getattr(campaign, key) != plan.get(key) for key in ("task_text", "order_id", "mode", "config_profile_id", "configuration_hash"))
            or canonical_json(campaign.caps) != canonical_json(plan.get("caps"))
            or content_hash(frozen) != campaign.configuration_hash
            or bound.get("registration_id") != plan.get("registration_id")
            or registration_id not in ("orders-v1", plan.get("registration_id"))
            or plan.get("source_mode") != source_mode or fixture_id != plan.get("fixture_id")
            or recipe is None or content_hash(recipe) != plan.get("scenario_hash")
            or policy is None or policy.version != plan.get("policy_version") or policy.policy_hash != plan.get("policy_hash")
            or content_hash(policy.content) != plan.get("policy_hash") or policy.decision != "BASELINE"):
        raise StoreConflict("Native execution differs from its declared task, source, recipe, policy or limits")
    identity = _binding(provider)
    if (content_hash(identity) != plan.get("execution_identity_hash")
            or identity["source_hash"] != plan.get("candidate_source_hash")):
        raise StoreConflict("Native execution binding differs from its declared candidate")
    if actor is not None and (type(actor) is not NativeActor or actor.provider is not provider):
        raise StoreConflict("Native actor override differs from its explicit process binding")
    prior = [row for row in store.list_records("episodes") if row.get("campaign_id") == campaign.campaign_id]
    required = plan.get("required_trials")
    if type(trial_index) is not int or type(required) is not int or required not in (1, 3) or len(prior) != trial_index:
        raise StoreConflict("Native execution cannot repeat or skip its declared attempts")
    if required == 1:
        if purpose != "discovery" or trial_index != 0 or study_id is not None or plan.get("scenario_manifest_hash") is not None:
            raise StoreConflict("Native healthy plan allows one explicit fresh trial")
    else:
        execution = store.get_record("regression_executions", study_id) if study_id else None
        if (purpose != "reproduction" or trial_index not in range(3) or not execution
                or execution.get("status") != "RUNNING" or execution.get("mode") != "FRESH_SANDBOX"
                or execution.get("explicit_action") is not True
                or execution.get("registration_id") != plan["registration_id"]
                or execution.get("configuration_hash") != campaign.configuration_hash
                or execution.get("manifest_hash") != plan.get("scenario_manifest_hash")
                or execution.get("episode_ids") != [row["episode_id"] for row in prior]):
            raise StoreConflict("Native regression requires its admitted three-trial fresh execution")
    registry = AgentRegistry(store)
    registration = registry.verify(plan["registration_id"], frozen)
    chosen = registry.reviewed_actor(registration.registration_id, provider=provider, model_id=MODEL_ID)
    descriptor = {"kind": "reviewed_native_user_agent", "registration_id": registration.registration_id,
                  "adapter_entrypoint_id": ENTRYPOINT, "configuration_hash": campaign.configuration_hash,
                  "plan_hash": raw["plan_hash"], "execution_identity_hash": content_hash(identity),
                  "candidate_source_hash": identity["source_hash"], "offline_fixture": True}
    return chosen, registration.registration_id, source_mode, MODEL_ID, None, descriptor
