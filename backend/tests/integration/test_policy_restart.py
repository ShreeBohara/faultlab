"""Offline acceptance fixtures verify persistence, not empirical learning gain.

Promotion's scientific predicates are tested in the lab suite. Here its trusted
commit seam receives labeled fixture decisions, then a new coordinator and real
HTTP EpisodeRunner must consume exactly the durable accepted policy. Provider
responses below are local fixtures; no sponsor/provider transport is initialized.
"""
import asyncio
from dataclasses import replace
import json

import pytest

from app.adapters.business_tools import WorldClient
from app.config import Settings
from app.contracts.models import CampaignRequest, CandidatePolicy, FaultSpec, canonical_json
from app.lab.coordinator import LabCoordinator
from app.lab.promotion import commit_promotion
from app.lab.runner import EpisodeRunner
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration


def create(coordinator, mode="learn"):
    return coordinator.create(CampaignRequest(task_text="Upgrade this order to express and confirm it truthfully.",
        order_id="restart-order", mode=mode, config_profile_id="live-v1"))


def propose(coordinator, parent, *, hook="before_confirmation"):
    steps = ([{"op": "require_receipt", "service": "orders", "status": "SUCCEEDED"}]
        if hook == "before_confirmation" else [{"op": "read_current_operation"}])
    candidate = CandidatePolicy.model_validate_json(canonical_json({"parent_version": parent,
        "rules": [{"hook": hook, "when": "always", "steps": steps}]}))
    return coordinator.policies.proposal(candidate, parent=parent,
        raw="OFFLINE_RESTART_FIXTURE: local contract test, not a generated learning result", episode_ids=[], author="manual")


def install_accepted_fixture(coordinator):
    campaign = create(coordinator)
    candidate = propose(coordinator, campaign.active_policy_version)
    commit_promotion(coordinator.store, coordinator.policies, campaign, candidate, "ACCEPTED",
        "OFFLINE_FIXTURE: exercise the already-validated commit boundary only", evaluation_ref="offline-fixture-evaluation")
    return campaign, coordinator.policies.get(candidate.version)


def test_accepted_policy_survives_restart_and_rejected_stale_candidates_do_not_replace_it(tmp_path):
    async def run():
        settings = Settings(faultlab_artifact_dir=str(tmp_path / "lab"), wandb_model="openai/gpt-oss-120b")
        original = LabCoordinator(settings)
        campaign = create(original)
        baseline_before = original.policies.baseline().model_dump(mode="json")
        candidate = propose(original, "policy-v0")
        stale = propose(original, "policy-v0", hook="after_upgrade_response")
        commit_promotion(original.store, original.policies, campaign, candidate, "ACCEPTED",
            "OFFLINE_FIXTURE: accepted commit", evaluation_ref="offline-accepted-evaluation")
        accepted = original.policies.get(candidate.version)
        rejected = propose(original, accepted.version, hook="after_upgrade_response")
        commit_promotion(original.store, original.policies, campaign, rejected, "REJECTED",
            "OFFLINE_FIXTURE: reject an inferior candidate", evaluation_ref="offline-rejected-evaluation")
        decisions_before = original.store.list_records("promotion_decisions")
        with pytest.raises(StoreConflict, match="Stale expected parent"):
            commit_promotion(original.store, original.policies, campaign, stale, "ACCEPTED",
                "OFFLINE_FIXTURE: stale candidate must not commit", evaluation_ref="offline-stale-evaluation")
        assert original.store.list_records("promotion_decisions") == decisions_before
        assert original.policies.get(stale.version).decision == "PROPOSED"
        assert original.policies.get(rejected.version).decision == "REJECTED"
        assert original.store.get_pointer(f"accepted-policy:{campaign.configuration_hash}") == accepted.version
        accepted_before = accepted.model_dump(mode="json")
        await original.close()

        restarted = LabCoordinator(settings)
        for mode in ("learn", "compare"):
            fresh = create(restarted, mode)
            assert fresh.campaign_id != campaign.campaign_id
            assert fresh.configuration_hash == campaign.configuration_hash
            assert fresh.active_policy_version == accepted.version
            assert fresh.state == "IDLE" and fresh.latest_episode_id is None
            assert restarted.store.get_pointer(f"active-policy:{fresh.campaign_id}") == accepted.version
        baseline_campaign = create(restarted, "baseline")
        assert baseline_campaign.active_policy_version == "policy-v0"
        assert restarted.policies.baseline().model_dump(mode="json") == baseline_before
        assert restarted.policies.get(accepted.version).model_dump(mode="json") == accepted_before
        assert restarted.store.list_records("episodes") == []
        assert restarted.active_id is None and restarted.tasks == {}
        await restarted.close()
    asyncio.run(run())


def test_policy_reuse_requires_matching_frozen_model_configuration(tmp_path):
    async def run():
        settings = Settings(faultlab_artifact_dir=str(tmp_path / "lab"), wandb_model="openai/gpt-oss-120b")
        original = LabCoordinator(settings)
        campaign, accepted = install_accepted_fixture(original)
        await original.close()
        changed = LabCoordinator(replace(settings, wandb_model="offline-different-model-fixture"))
        fresh = create(changed)
        assert fresh.configuration_hash != campaign.configuration_hash
        assert fresh.active_policy_version == "policy-v0"
        with pytest.raises(StoreConflict, match="No accepted policy"):
            create(changed, "compare")
        assert changed.store.get_pointer(f"accepted-policy:{campaign.configuration_hash}") == accepted.version
        assert changed.store.list_records("episodes") == []
        await changed.close()
    asyncio.run(run())


@pytest.mark.localhost_http
def test_fresh_http_world_and_actor_conversation_after_coordinator_restart(tmp_path, simulator_server):
    url, world_app = simulator_server

    class OfflineProvider:
        """A stateless scripted author driven only by this invocation's public ledger."""
        def __init__(self): self.initial_messages = []; self.calls = 0
        async def complete(self, messages, **kwargs):
            self.calls += 1
            public = json.loads(messages[-1]["content"])["observations"]
            if not public:
                self.initial_messages.append(messages)
                action = {"kind": "tool", "tool": "update_order", "arguments": {"desired_shipping": "express"}}
            elif len(public) == 1:
                action = {"kind": "tool", "tool": "send_confirmation", "arguments": {}}
            else:
                action = {"kind": "report", "report": {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED",
                    "overall": "COMPLETED", "evidence_ids": [item["evidence_id"] for item in public], "next_action": {"kind": "NONE"}}}
            return RuntimeGeneration(canonical_json(action), "openai/gpt-oss-120b", input_tokens=100, output_tokens=30)

    async def run():
        settings = Settings(faultlab_artifact_dir=str(tmp_path / "lab"), wandb_model="openai/gpt-oss-120b",
            faultlab_simulator_url=url, faultlab_control_token="integration-control")
        coordinator = LabCoordinator(settings)
        _, accepted = install_accepted_fixture(coordinator)
        provider = OfflineProvider()
        results = []
        source_inputs = []
        original_report = None
        for index in range(2):
            campaign = create(coordinator)
            assert campaign.active_policy_version == accepted.version
            world_client = WorldClient(url, "integration-control")
            runner = EpisodeRunner(coordinator.store, world_client, provider)
            trial = await runner.run(campaign, FaultSpec(seed=51, primitives=[]), coordinator.policies.get(campaign.active_policy_version),
                purpose="reproduction", arm="L", trial_index=index, source_mode="offline_fixture")
            assert trial.lifecycle == "COMPLETED" and trial.outcome == "COMPLETED"
            assert trial.policy_hash == accepted.policy_hash
            assert trial.usage.model_calls == 3 and trial.usage.http_attempts == 2
            episode = coordinator.store.get_record("episodes", trial.episode_id)
            assert episode["source_mode"] == "offline_fixture"
            inputs = coordinator.store.get_record("private_episode_inputs", trial.episode_id)
            source_inputs.append(inputs["intent"])
            results.append(trial)
            if index == 0: original_report = episode["report"]
            await world_client.close()
            await coordinator.close()
            if index == 0:
                world_count = len(list(world_app.state.store.directory.glob("*.sqlite3")))
                coordinator = LabCoordinator(settings)
                assert provider.calls == 3
                assert len(list(world_app.state.store.directory.glob("*.sqlite3"))) == world_count
                assert coordinator.store.get_record("episodes", trial.episode_id)["report"] == original_report
                assert coordinator.active_id is None and not coordinator.tasks

        assert len({trial.world_id for trial in results}) == 2
        assert len({trial.episode_id for trial in results}) == 2
        for key in ("task_id", "upgrade_operation_id", "notification_operation_id", "upgrade_idempotency_key", "notification_idempotency_key"):
            assert source_inputs[0][key] != source_inputs[1][key]
        assert len(provider.initial_messages) == 2
        assert all(json.loads(messages[-1]["content"])["observations"] == [] for messages in provider.initial_messages)
        assert source_inputs[0]["task_id"] not in canonical_json(provider.initial_messages[1])
        assert all(trial.usage.model_calls == 3 for trial in results)
        assert provider.calls == 6

    asyncio.run(run())
