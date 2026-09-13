"""Offline fixtures only; these records are never published as measured learning."""
from types import SimpleNamespace
import pytest

from app.config import Settings
from app.contracts.models import CampaignBudget, Counterexample, FaultSpec, content_hash
from app.lab.configuration import frozen_configuration
from app.lab.policies import PolicyRepository
from app.lab.regressions import RegressionCompiler
from app.lab.storage import LabStore
from app.integrations.registry import AgentRegistry, freeze_target_configuration


@pytest.fixture
def store():
    value = LabStore(":memory:")
    yield value
    value.db.close()


@pytest.fixture
def source_configuration():
    return frozen_configuration(Settings(wandb_model="openai/gpt-oss-120b"), CampaignBudget(), "live-v1")


@pytest.fixture
def registry(store):
    return AgentRegistry(store)


@pytest.fixture
def external(registry, source_configuration):
    target = freeze_target_configuration(source_configuration, "openai/gpt-oss-120b")
    return registry.register_smolagents(target), target


@pytest.fixture
def source_registration(registry, source_configuration):
    return registry.register_reference(source_configuration, internal_smoke=True)


@pytest.fixture
def baseline(store):
    return PolicyRepository(store).baseline()


@pytest.fixture
def bundle(tmp_path, store, source_configuration, baseline):
    configuration_hash = content_hash(source_configuration)
    store.put_record("configurations", configuration_hash, source_configuration, immutable=True)
    campaign = SimpleNamespace(campaign_id="offline-campaign", configuration_hash=configuration_hash)
    recipe = FaultSpec.model_validate_json('{"seed":42,"primitives":[{"kind":"F1","target_tool":"update_order","target_service":"orders","occurrence":1,"parameters":{"response_delay_ms":1500}}]}')
    counter = Counterexample(counterexample_id="offline-counterexample", campaign_id=campaign.campaign_id,
        agent_registration_id="orders-v1", source_episode_id="offline-source", target_invariant="C3", scenario_hash=content_hash(recipe),
        configuration_hash=configuration_hash, report_ref=None, verdict_ref="offline-verdict")
    store.put_record("private_episode_inputs", "offline-source", {"fixture_id": "standard-v1"})
    compiler = RegressionCompiler(store)
    manifest = compiler.compile(campaign, counter, baseline, recipe, recipe, [])
    directory = tmp_path / "bundle"
    compiler.export(manifest.bundle_id, directory)
    return directory, manifest
