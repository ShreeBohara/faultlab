"""Orchestration fixtures; no live external measurements are produced here."""
import asyncio
from copy import deepcopy

import pytest

from app.contracts.models import FaultSpec, RecoveryPolicy, PolicyVersion, TrialResult, Usage, content_hash, canonical_json
from app.integrations.portability import PortabilityStudy
from app.referee.manifests import load_manifest


@pytest.fixture
def accepted(store, baseline):
    # Deliberately labeled offline acceptance fixture, never a generated result.
    content = RecoveryPolicy.model_validate_json('{"parent_version":"policy-v0","rules":[{"hook":"before_confirmation","when":"always","steps":[{"op":"require_receipt","service":"orders","status":"SUCCEEDED"}]}]}')
    policy = PolicyVersion(version="offline-accepted-fixture", parent_version=baseline.version, content=content, policy_hash=content_hash(content),
        author="manual", raw_proposal_ref="offline-fixture", development_episode_ids=[], decision="ACCEPTED")
    store.put_record("policies", policy.version, policy)
    return policy


@pytest.fixture
def frozen(external, accepted):
    registration, _ = external
    manifest = deepcopy(load_manifest("portability"))
    manifest["external_identity"] = {"status": "FROZEN", "registration_id": registration.registration_id, "source_hash": registration.source_hash,
        "adapter_hash": registration.adapter_hash, "configuration_hash": registration.configuration_hash}
    manifest["manifest_hash"] = content_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
    value = {"schema_version": "faultlab-external-freeze/v1", "status": "FROZEN", "core_freeze_hash": "a" * 64,
        "manifest": manifest, "registration": registration.model_dump(mode="json"), "policy_hash": accepted.policy_hash}
    value["freeze_hash"] = content_hash(value)
    return value


def arguments(store, registry, external, source_registration, baseline, accepted, frozen, *, invalid_at=None):
    registration, target = external
    calls = []
    async def execute(case, registered, policy, index, arm):
        number = len(calls)
        calls.append((case["case_id"], index, arm, policy.policy_hash, registered.configuration_hash))
        episode_id, world_id = f"external-offline-{number}", f"world-offline-{number}"
        recipe = FaultSpec.model_validate_json(canonical_json(case["fault_spec"]))
        store.put_record("episodes", episode_id, {"campaign_id": "offline-portability", "world_id": world_id,
            "configuration_hash": target["schema_version"] if number == invalid_at else registration.configuration_hash,
            "agent_registration_id": registration.registration_id, "experiment_purpose": "portability", "split": "final_audit", "source_mode": "offline_fixture"})
        return TrialResult(episode_id=episode_id, world_id=world_id, scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash,
            arm=arm, trial_index=index, lifecycle="COMPLETED", outcome="VIOLATION" if arm == "L" else "COMPLETED", failed_checks=["C3"] if arm == "L" else [],
            fault_scheduled=bool(recipe.primitives), fault_triggered=bool(recipe.primitives), usage=Usage(model_calls=2, actor_calls=2))
    return calls, dict(external_freeze=frozen, source_registration_id=source_registration.registration_id,
        target_registration_id=registration.registration_id, target_configuration=target, baseline_policy=baseline,
        accepted_policy=accepted, run_fresh=execute, explicit_live=True, source_mode="offline_fixture")


def test_six_by_three_pairs_frozen_unchanged_all_attempts_retained(store, registry, external, source_registration, baseline, accepted, frozen):
    calls, kwargs = arguments(store, registry, external, source_registration, baseline, accepted, frozen)
    study = PortabilityStudy(store, registry)
    result = asyncio.run(study.run(**kwargs))
    assert len(calls) == 36 and len(result.trial_pairs) == 18
    assert [call[2] for call in calls[:4]] == ["B0", "L", "L", "B0"]
    assert {c[3] for c in calls if c[2] == "L"} == {accepted.policy_hash}
    assert len({c[4] for c in calls}) == 1
    assert result.status == "INCOMPLETE"  # Offline fixture cannot establish external acceptance.
    metrics = store.get_record("portability_metrics", result.portability_id)
    assert metrics["attempted"] == 36 and metrics["by_arm"]["L"]["VIOLATION"] == 18
    assert metrics["by_arm"]["B0"]["COMPLETED"] == 18
    assert not metrics["fresh_external_acceptance"]
    assert len(store.get_record("portability_attempts", result.portability_id)["attempts"]) == 36
    with pytest.raises(ValueError, match="already has"):
        asyncio.run(study.run(**kwargs))
    assert len(calls) == 36


def test_invalid_pair_ends_without_favorable_retry(store, registry, external, source_registration, baseline, accepted, frozen):
    calls, kwargs = arguments(store, registry, external, source_registration, baseline, accepted, frozen, invalid_at=0)
    result = asyncio.run(PortabilityStudy(store, registry).run(**kwargs))
    assert result.status == "INCOMPLETE" and len(calls) == 2
    assert len(store.get_record("portability_attempts", result.portability_id)["attempts"]) == 2


def test_stop_preserves_partial_pair(store, registry, external, source_registration, baseline, accepted, frozen):
    calls, kwargs = arguments(store, registry, external, source_registration, baseline, accepted, frozen)
    kwargs["stop"] = lambda: len(calls) == 1
    result = asyncio.run(PortabilityStudy(store, registry).run(**kwargs))
    assert result.status == "INCOMPLETE" and len(calls) == 1
    assert len(result.trial_pairs) == 0
    assert len(store.get_record("portability_attempts", result.portability_id)["attempts"]) == 1


@pytest.mark.parametrize("change", ["no_explicit", "retuned_policy", "changed_manifest", "internal_smoke", "new_target_campaign"])
def test_unsupported_or_unfrozen_study_rejected_before_calls(store, registry, external, source_registration, baseline, accepted, frozen, change):
    calls, kwargs = arguments(store, registry, external, source_registration, baseline, accepted, frozen)
    if change == "no_explicit": kwargs["explicit_live"] = False
    if change == "retuned_policy": kwargs["accepted_policy"] = accepted.model_copy(update={"policy_hash": "f" * 64})
    if change == "changed_manifest": kwargs["external_freeze"] = {**frozen, "policy_hash": "f" * 64}
    if change == "internal_smoke":
        kwargs["target_registration_id"] = source_registration.registration_id
        kwargs["target_configuration"] = store.get_record("configurations", source_registration.configuration_hash)
    if change == "new_target_campaign": kwargs["policy_source"] = "new_target_campaign"
    with pytest.raises(ValueError): asyncio.run(PortabilityStudy(store, registry).run(**kwargs))
    assert calls == []
