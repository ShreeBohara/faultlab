"""Native source must be explicitly bound before any world or child can run."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, content_hash
from app.integrations.registry import AGENT_ENTRYPOINTS, AgentRegistry
from app.lab.policies import PolicyRepository
from app.lab.runner import EpisodeRunner, resolve_execution
from app.lab.storage import LabStore
from app.native_agents.actor import NativeActor
from app.native_agents.registration import (
    CONFIG_FIELDS, ENTRYPOINT, MODEL_ID, create_native_campaign,
    freeze_native_configuration, register_native,
)
from app.native_agents.source import read_agent
from app.native_agents.transport import NativeAgentProvider


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def admitted(tmp_path):
    # Even the admission positive case must not import operator code in parent.
    authored = tmp_path / "outside-agent.py"
    authored.write_text('raise AssertionError("OPERATOR_CODE_IMPORTED_IN_PARENT")\n'
                        'def build_agent(model, tools):\n    return None\n')
    output = tmp_path / "output"
    output.mkdir()
    snapshot = read_agent(authored).freeze(output)
    provider = NativeAgentProvider(snapshot, output / "work")
    store = LabStore(":memory:")
    coordinator = SimpleNamespace(settings=Settings(), store=store, policies=PolicyRepository(store),
                                  save=lambda campaign: store.put_record("campaigns", campaign.campaign_id, campaign))
    recipe = FaultSpec(seed=105, primitives=[])
    request = CampaignRequest(mode="baseline", task_text="Upgrade this order and confirm truthfully.",
                              order_id="registration-order", config_profile_id="offline-v1")
    campaign = create_native_campaign(coordinator, request, provider,
                                      scenario_hash=content_hash(recipe), required_trials=1)
    configuration = store.get_record("configurations", campaign.configuration_hash)
    bound = store.get_record("campaign_registrations", campaign.campaign_id)["registration_id"]
    yield SimpleNamespace(store=store, coordinator=coordinator, provider=provider, snapshot=snapshot,
                          campaign=campaign, configuration=configuration, registration_id=bound,
                          recipe=recipe, policy=coordinator.policies.baseline(), request=request)
    store.close()


def _resolve(admitted, **changes):
    args = dict(arm="B0", purpose="discovery", study_id=None, source_mode="offline_fixture",
                registration_id="orders-v1", actor=None, actor_context_protocol=None,
                offline_fixture=True, provider=admitted.provider, recipe=admitted.recipe,
                policy=admitted.policy, fixture_id="standard-v1", trial_index=0)
    args.update(changes)
    return resolve_execution(admitted.store, admitted.campaign, admitted.configuration, **args)


def test_true_native_identity_and_explicit_binding_without_parent_import(admitted):
    registry = AgentRegistry(admitted.store)
    registration = registry.verify(admitted.registration_id, admitted.configuration)
    assert registration.adapter_entrypoint_id == ENTRYPOINT
    assert registration.model == MODEL_ID
    assert registration.source_hash != admitted.snapshot.source_hash  # Candidate + framework.
    assert registration.provenance_class == "external"
    assert ENTRYPOINT not in AGENT_ENTRYPOINTS.values()
    chosen, selected, source_mode, model, context, descriptor = _resolve(admitted)
    assert type(chosen) is NativeActor and chosen.provider is admitted.provider
    assert selected == admitted.registration_id and source_mode == "offline_fixture"
    assert model == MODEL_ID and context is None
    assert descriptor["candidate_source_hash"] == admitted.snapshot.source_hash
    assert admitted.store.list_records("episodes") == []
    assert admitted.provider.records == {}


@pytest.mark.parametrize("method", ["register_reference", "register_smolagents"])
def test_native_candidate_cannot_impersonate_reviewed_historical_agents(admitted, method):
    before = admitted.store.list_records("agent_registrations")
    with pytest.raises(ValueError, match="native"):
        getattr(AgentRegistry(admitted.store), method)(admitted.configuration)
    assert admitted.store.list_records("agent_registrations") == before


def test_factory_requires_explicit_binding_and_saved_plan(admitted):
    registry = AgentRegistry(admitted.store)
    with pytest.raises(ValueError, match="binding"):
        registry.reviewed_actor(admitted.registration_id)
    admitted.store.db.execute("DELETE FROM records WHERE kind='native_campaign_plans'")
    with pytest.raises(ValueError, match="plan"):
        registry.reviewed_actor(admitted.registration_id, provider=admitted.provider)


@pytest.mark.anyio
@pytest.mark.parametrize("damage", ["missing_plan", "missing_provenance", "model_only", "wrong_source", "wrong_recipe", "live_label", "reference_actor", "repeat_attempt"])
async def test_native_admission_refuses_before_world_or_child(admitted, damage):
    changes = {"source_mode": "offline_fixture"}
    provider = admitted.provider
    if damage == "missing_plan":
        admitted.store.db.execute("DELETE FROM records WHERE kind='native_campaign_plans'")
    elif damage == "missing_provenance":
        admitted.store.db.execute("DELETE FROM records WHERE kind='campaign_provenance'")
    elif damage == "model_only":
        admitted.store.db.execute("DELETE FROM records WHERE kind IN ('native_campaign_plans', 'campaign_provenance', 'campaign_registrations')")
        legacy = {key: value for key, value in admitted.configuration.items() if key not in CONFIG_FIELDS}
        admitted.campaign.configuration_hash = content_hash(legacy)
        admitted.store.put_record("configurations", admitted.campaign.configuration_hash, legacy)
        provider = None
    elif damage == "wrong_source":
        admitted.snapshot.path.chmod(0o600)
        admitted.snapshot.path.write_text("def build_agent(model, tools): return None\n")
    elif damage == "wrong_recipe":
        changes["recipe"] = FaultSpec(seed=999, primitives=[])
    elif damage == "live_label":
        changes["source_mode"] = "live"
    elif damage == "reference_actor":
        from app.adapters.prototype import run_prototype
        changes["actor"] = run_prototype
    elif damage == "repeat_attempt":
        changes["trial_index"] = 1

    class NoWorld:
        calls = 0

        async def create(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("Admission created a world")

    world = NoWorld()
    runner = EpisodeRunner(admitted.store, world, provider, offline_fixture=True)
    selected_recipe = changes.pop("recipe", admitted.recipe)
    with pytest.raises((ValueError, RuntimeError)):
        await runner.run(admitted.campaign, selected_recipe, admitted.policy, **changes)
    assert world.calls == 0
    assert admitted.store.list_records("episodes") == []
    assert admitted.provider.records == {}


def test_different_candidate_and_timeout_have_separate_frozen_identities(admitted, tmp_path):
    source = tmp_path / "other.py"
    source.write_text("def build_agent(model, tools): return None\n")
    output = tmp_path / "other-output"
    output.mkdir()
    candidate = NativeAgentProvider(read_agent(source).freeze(output), output / "work")
    with pytest.raises(ValueError, match="binding|candidate"):
        _resolve(admitted, provider=candidate)
    limits = NativeAgentProvider(admitted.snapshot, output / "other-work", turn_timeout_seconds=0.5)
    changed = freeze_native_configuration(admitted.configuration, limits)
    assert changed["native_execution_identity_hash"] != admitted.configuration["native_execution_identity_hash"]
    assert content_hash(changed) != admitted.campaign.configuration_hash
    with pytest.raises(ValueError, match="binding|candidate"):
        _resolve(admitted, provider=limits)


def test_regression_plan_requires_admitted_execution_and_matching_manifest(admitted):
    manifest_hash = "a" * 64
    campaign = create_native_campaign(admitted.coordinator, admitted.request, admitted.provider,
        scenario_hash=content_hash(admitted.recipe), scenario_manifest_hash=manifest_hash, required_trials=3)
    admitted.campaign = campaign
    admitted.configuration = admitted.store.get_record("configurations", campaign.configuration_hash)
    kwargs = {"purpose": "reproduction", "study_id": "regression-proof"}
    with pytest.raises(ValueError, match="admitted"):
        _resolve(admitted, **kwargs)
    execution = {"status": "RUNNING", "mode": "FRESH_SANDBOX", "explicit_action": True,
                 "registration_id": admitted.registration_id, "configuration_hash": campaign.configuration_hash,
                 "manifest_hash": "b" * 64, "episode_ids": []}
    admitted.store.put_record("regression_executions", "regression-proof", execution)
    with pytest.raises(ValueError, match="admitted"):
        _resolve(admitted, **kwargs)
    execution["manifest_hash"] = manifest_hash
    admitted.store.put_record("regression_executions", "regression-proof", execution)
    assert type(_resolve(admitted, **kwargs)[0]) is NativeActor
    assert admitted.store.list_records("episodes") == []


def test_invalid_plan_request_leaves_no_native_campaign(admitted):
    before = admitted.store.list_records("campaigns")
    for required in (True, 2, 4):
        with pytest.raises(ValueError):
            create_native_campaign(admitted.coordinator, admitted.request, admitted.provider,
                                   scenario_hash=content_hash(admitted.recipe), required_trials=required)
    assert admitted.store.list_records("campaigns") == before


def test_registration_cannot_attest_to_modified_shared_semantics(admitted):
    changed = deepcopy(admitted.configuration)
    changed["contract_hash"] = "f" * 64
    before = admitted.store.list_records("agent_registrations")
    with pytest.raises(ValueError, match="semantics"):
        register_native(admitted.store, changed, admitted.provider)
    assert admitted.store.list_records("agent_registrations") == before
