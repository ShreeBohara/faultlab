import asyncio
from hashlib import sha256
import importlib.util
import json

import pytest

from app.contracts.models import TrialResult, Usage, content_hash, canonical_json
from app.integrations.regression_runner import RegressionRunner, inspect_bundle, TRUSTED_TEMPLATE


def rewrite_manifest(directory, edit=None, changed_file=None):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if changed_file:
        data = (directory / changed_file).read_bytes()
        entry = next(item for item in manifest["files"] if item["path"] == changed_file)
        entry.update(sha256=sha256(data).hexdigest(), size_bytes=len(data))
    if edit: edit(manifest)
    manifest["manifest_hash"] = content_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
    manifest_path.write_text(canonical_json(manifest))


def test_validation_playback_and_template_collection_have_zero_effects(bundle, store, registry, external):
    directory, manifest = bundle
    registration, target = external
    runner = RegressionRunner(store, registry)
    verified = runner.validate(directory, target, registration.registration_id)
    assert verified.bundle == manifest
    assert verified.source_configuration["actor_prompt_hash"] != target["actor_prompt_hash"]
    assert verified.execution.mode == "VALIDATE_ONLY"
    playback = runner.playback(directory, target, registration.registration_id)
    assert playback.mode == "RECORDED_PLAYBACK"
    for execution in (verified.execution, playback):
        assert execution.usage == Usage()
        assert not execution.episode_ids and not execution.world_ids
    assert store.list_records("episodes") == []
    # Execute only the installed reviewed module, never a bundle-selected import.
    spec = importlib.util.spec_from_file_location("reviewed_static_test", TRUSTED_TEMPLATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.test_bundle_inventory_is_data_only)
    assert store.list_records("episodes") == []


@pytest.mark.parametrize("path", ["../outside.py", "/tmp/agent.py", "https://example.org/agent.py", "harness/../../evil.py", "harness\\evil.py"])
def test_paths_rejected_even_with_rehashed_manifest(bundle, path):
    directory, _ = bundle
    rewrite_manifest(directory, lambda m: m["files"][0].update(path=path))
    with pytest.raises(ValueError): inspect_bundle(directory)


@pytest.mark.parametrize("field", ["schema_hash", "harness_hash", "contract_hash", "configuration_hash", "policy_hash", "dependency_lock_hash"])
def test_digest_mismatch_rejected_before_execution(bundle, field):
    directory, _ = bundle
    rewrite_manifest(directory, lambda m: m.update({field: "f" * 64}))
    with pytest.raises(ValueError): inspect_bundle(directory)


def test_rehashed_attacker_runner_is_not_trusted(bundle):
    directory, _ = bundle
    target = directory / "harness/test_regression.py"
    target.write_text("raise AssertionError('must never execute bundled Python')\n")
    rewrite_manifest(directory, lambda m: m.update(harness_hash=sha256(target.read_bytes()).hexdigest()), "harness/test_regression.py")
    with pytest.raises(ValueError, match="Untrusted"): inspect_bundle(directory)


def test_symlink_and_unexpected_inventory_rejected(bundle, tmp_path):
    directory, _ = bundle
    original = (directory / "trials.json").read_text()
    outside = tmp_path / "outside.json"; outside.write_text(original)
    (directory / "trials.json").unlink()
    (directory / "trials.json").symlink_to(outside)
    with pytest.raises(ValueError, match="Symlink"): inspect_bundle(directory)
    (directory / "trials.json").unlink(); (directory / "trials.json").write_text(original)
    (directory / "install.py").write_text("pass")
    with pytest.raises(ValueError, match="inventory"): inspect_bundle(directory)


def test_untrusted_import_or_url_configuration_rejected(bundle):
    directory, _ = bundle
    config = json.loads((directory / "configuration.json").read_text())
    config["provider_url"] = "https://example.org/stolen"
    (directory / "configuration.json").write_text(canonical_json(config))
    rewrite_manifest(directory, lambda m: m.update(configuration_hash=content_hash(config)), "configuration.json")
    with pytest.raises(ValueError, match="Unreviewed"): inspect_bundle(directory)


def test_source_provenance_may_differ_from_independently_reviewed_target(bundle, store, registry, external):
    directory, _ = bundle
    registration, target = external
    historical = json.loads((directory / "configuration.json").read_text())
    historical.update(actor_prompt_hash="a" * 64, source_hash="b" * 64, adapter_hash="c" * 64, dependency_lock_hash="d" * 64)
    (directory / "configuration.json").write_text(canonical_json(historical))
    rewrite_manifest(directory, lambda m: m.update(configuration_hash=content_hash(historical), dependency_lock_hash="d" * 64), "configuration.json")
    checked = RegressionRunner(store, registry).validate(directory, target, registration.registration_id)
    assert checked.source_configuration["dependency_lock_hash"] != checked.target_configuration["dependency_lock_hash"]
    assert checked.execution.usage == Usage()


def test_duplicate_json_keys_are_rejected(bundle):
    directory, _ = bundle
    content = (directory / "manifest.json").read_text()
    (directory / "manifest.json").write_text(content.replace('"bundle_id":', '"bundle_id":"duplicate","bundle_id":', 1))
    with pytest.raises(ValueError, match="Duplicate JSON"): inspect_bundle(directory)


def trial(recipe, policy, index, *, duplicate=False, outcome="VIOLATION"):
    return TrialResult(episode_id="fresh-0" if duplicate else f"fresh-{index}", world_id="world-0" if duplicate else f"world-{index}",
        scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm="B0", trial_index=index,
        lifecycle="COMPLETED", outcome=outcome, failed_checks=["C3"] if outcome == "VIOLATION" else [], fault_scheduled=True, fault_triggered=True,
        usage=Usage(model_calls=2, actor_calls=2, http_attempts=3))


def persist_trial(store, registration, result, *, fixture_id="standard-v1"):
    store.put_record("episodes", result.episode_id, {"episode_id": result.episode_id, "world_id": result.world_id,
        "campaign_id": "offline-regression", "configuration_hash": registration.configuration_hash,
        "agent_registration_id": registration.registration_id, "policy_hash": result.policy_hash, "source_mode": "offline_fixture"})
    store.put_record("private_episode_inputs", result.episode_id, {"fixture_id": fixture_id})
    return result


def test_fresh_requires_explicit_action_and_exact_policy(bundle, store, registry, external, baseline):
    directory, _ = bundle
    registration, target = external
    runner = RegressionRunner(store, registry)
    calls = []
    async def run_fresh(*args): calls.append(args)
    with pytest.raises(ValueError, match="explicit"):
        asyncio.run(runner.execute(directory, target, registration.registration_id, explicit_live=False, profile_id="sandbox-v1", run_fresh=run_fresh))
    with pytest.raises(ValueError, match="exact"):
        asyncio.run(runner.execute(directory, target, registration.registration_id, explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh,
            policy_version=baseline.model_copy(update={"policy_hash": "f" * 64})))
    assert calls == []


def test_fresh_three_trials_retained_with_new_ids_and_no_rerun(bundle, store, registry, external):
    directory, _ = bundle
    registration, target = external
    runner = RegressionRunner(store, registry)
    calls = []
    async def run_fresh(recipe, registered, policy, index, *, fixture_id):
        calls.append(index)
        return persist_trial(store, registered, trial(recipe, policy, index), fixture_id=fixture_id)
    result = asyncio.run(runner.execute(directory, target, registration.registration_id, explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh, execution_id="explicit-offline-fixture"))
    assert calls == [0, 1, 2] and result.status == "COMPLETED"
    assert len(set(result.world_ids)) == 3
    assert result.usage.model_calls == 6
    assert store.get_record("regression_assertions", result.execution_id)["reproduced"]
    with pytest.raises(ValueError, match="already used"):
        asyncio.run(runner.execute(directory, target, registration.registration_id, explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh, execution_id=result.execution_id))
    assert calls == [0, 1, 2]


def test_duplicate_world_and_failed_attempt_remain_incomplete(bundle, store, registry, external):
    directory, _ = bundle
    registration, target = external
    async def run_fresh(recipe, registered, policy, index, *, fixture_id): return persist_trial(store, registered, trial(recipe, policy, index, duplicate=True), fixture_id=fixture_id)
    result = asyncio.run(RegressionRunner(store, registry).execute(directory, target, registration.registration_id,
        explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh))
    assert result.status == "INCOMPLETE" and len(result.episode_ids) == 2
    assert len(store.get_record("regression_attempts", result.execution_id)["trials"]) == 2
    assert not store.get_record("regression_assertions", result.execution_id)["reproduced"]


def test_reduced_f3_recipe_retains_original_history_fixture(bundle, store, registry, external):
    from app.contracts.models import FaultSpec
    directory, _ = bundle
    registration, target = external
    source = FaultSpec.model_validate_json('{"seed":42,"primitives":[{"kind":"F3","target_tool":"get_order","target_service":"orders","occurrence":1,"parameters":{"versions_back":1}}]}')
    retained = FaultSpec(seed=42, primitives=[])
    (directory / "source-recipe.json").write_text(canonical_json(source))
    (directory / "retained-recipe.json").write_text(canonical_json(retained))
    rewrite_manifest(directory, lambda m: m.update(source_recipe=source.model_dump(mode="json"), retained_recipe=retained.model_dump(mode="json"), fixture_id="history-v1"), "source-recipe.json")
    rewrite_manifest(directory, changed_file="retained-recipe.json")
    observed_fixtures = []
    async def run_fresh(recipe, registered, policy, index, *, fixture_id):
        assert not recipe.primitives
        observed_fixtures.append(fixture_id)
        result = trial(recipe, policy, index).model_copy(update={"fault_scheduled": False, "fault_triggered": False})
        return persist_trial(store, registered, result, fixture_id=fixture_id)
    result = asyncio.run(RegressionRunner(store, registry).execute(directory, target, registration.registration_id,
        explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh))
    assert result.status == "COMPLETED"
    assert observed_fixtures == ["history-v1"] * 3


def test_changed_reset_fixture_is_incomplete(bundle, store, registry, external):
    directory, _ = bundle
    registration, target = external
    async def run_fresh(recipe, registered, policy, index, *, fixture_id):
        return persist_trial(store, registered, trial(recipe, policy, index), fixture_id="history-v1")
    result = asyncio.run(RegressionRunner(store, registry).execute(directory, target, registration.registration_id,
        explicit_live=True, profile_id="sandbox-v1", run_fresh=run_fresh))
    assert result.status == "INCOMPLETE" and len(result.episode_ids) == 1
