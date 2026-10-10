"""Explicit native constructor conformance through unchanged orders evidence and scoring."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import shutil

import httpx

from app.adapters.business_tools import WorldClient
from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, content_hash, new_id
from app.examples.rejected_upgrade import (
    SIDECAR_NAME, _inspect_offline_bundle, _new_output, _trial_evidence,
    _write_json, inspect_example_bundle, rejection_recipe,
)
from app.examples.simulator import create_app
from app.integrations.registry import AgentRegistry
from app.integrations.regression_runner import RegressionRunner
from app.lab.budgets import CampaignLedger
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.native_agents.model import MODEL_ID, identity as model_identity
from app.native_agents.registration import create_native_campaign
from app.native_agents.source import read_agent
from app.native_agents.transport import NativeAgentProvider, valid_execution
from app.native_agents.report import write_report

TASK_TEXT = "Upgrade this order to express and send one truthful confirmation."


class _NativeRunner(EpisodeRunner):
    async def run(self, *args, **kwargs):
        if kwargs.get("source_mode", "offline_fixture") != "offline_fixture":
            raise ValueError("Native conformance cannot be labeled live")
        episode_id = kwargs.get("episode_id") or new_id("episode")
        try:
            return await super().run(*args, **{**kwargs, "episode_id": episode_id,
                                              "source_mode": "offline_fixture"})
        finally:
            record = self.provider.records.get(episode_id)
            if record is not None:
                value = {**record, "episode_id": episode_id}
                self.store.put_record("native_agent_executions", episode_id, value, immutable=True)
                self.store.append_event(episode_id, type="native_agent_execution", payload=value)


@asynccontextmanager
async def _environment(output, snapshot, timeout, recipe, scenario, required):
    settings = Settings(wandb_model=MODEL_ID, faultlab_artifact_dir=str(output / "state"))
    control = secrets.token_urlsafe(32)
    simulator = create_app(database_dir=output / "worlds", control_token=control, settings=settings)
    coordinator = LabCoordinator(settings)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                                    base_url="http://127.0.0.1:8001", trust_env=False) as client:
            provider = NativeAgentProvider(snapshot, output / "agent-work", turn_timeout_seconds=timeout)
            world = WorldClient("http://127.0.0.1:8001", control, client=client)
            runner = _NativeRunner(coordinator.store, world, provider, offline_fixture=True)
            coordinator.runner = runner
            campaign = create_native_campaign(coordinator,
                CampaignRequest(mode="baseline", config_profile_id="offline-v1",
                                task_text=TASK_TEXT, order_id="order-native-agent"),
                provider, scenario_hash=content_hash(recipe),
                scenario_manifest_hash=scenario["manifest_hash"] if scenario else None,
                required_trials=required)
            yield coordinator, campaign, runner, provider
    finally:
        await coordinator.close()


def _portable_copy(directory, output, expected_manifest_hash):
    portable = output / "portable"
    portable.mkdir()
    shutil.copytree(directory, portable / "bundle", symlinks=True)
    shutil.copy2(directory.parent / SIDECAR_NAME, portable / SIDECAR_NAME, follow_symlinks=False)
    _, copied = _inspect_offline_bundle(portable / "bundle")
    if copied.bundle.manifest_hash != expected_manifest_hash:
        raise ValueError("Scenario changed while snapshotting the native regression")
    (portable / "test_native_agent.py").write_bytes(
        Path(__file__).with_name("test_native_agent.py.txt").read_bytes())
    return portable


def _summarize(output, snapshot, coordinator, campaign, provider, recipe, required,
               healthy, scenario, execution, error):
    trials = []
    for episode in coordinator.store.list_campaign_episodes(campaign.campaign_id):
        row = _trial_evidence(coordinator.store, episode["episode_id"], recipe)
        record = coordinator.store.get_record("native_agent_executions", episode["episode_id"])
        execution_binding = coordinator.store.get_record("episode_executions", episode["episode_id"])
        row["native_agent_execution"] = record
        row["registered_execution"] = execution_binding
        if (not valid_execution(record, snapshot, provider.identity)
                or record.get("episode_id") != episode["episode_id"]
                or record["final_report"]["decoded_report"] != row["original_report"]
                or record["model_calls"] != (episode.get("usage") or {}).get("model_calls")
                or record["model_calls"] != (episode.get("usage") or {}).get("actor_calls")
                or not isinstance(execution_binding, dict)
                or execution_binding.get("kind") != "reviewed_native_user_agent"
                or execution_binding.get("configuration_hash") != campaign.configuration_hash
                or execution_binding.get("execution_identity_hash") != content_hash(provider.identity)
                or execution_binding.get("candidate_source_hash") != snapshot.source_hash):
            row["evidence_valid"] = False
            row["status"] = "INCOMPLETE"
            row["evidence_issues"].append("NATIVE_AGENT_EXECUTION_INCOMPLETE")
        trials.append(row)
    complete = (error is None and len(trials) == required
                and all(row["evidence_valid"] and row["status"] != "INCOMPLETE" for row in trials)
                and (healthy or (execution is not None and execution.status == "COMPLETED"
                                 and execution.manifest_hash == scenario["manifest_hash"])))
    if not complete:
        status = "INCOMPLETE"
    elif any(row["status"] == "VIOLATION" for row in trials):
        status = "VIOLATION"
    elif healthy and any(row["outcome"] != "COMPLETED" for row in trials):
        status, complete = "INCOMPLETE", False
    else:
        status = "PASS"
    identity = {"agent": snapshot.descriptor, "native_runtime": provider.identity,
                "configuration_hash": campaign.configuration_hash,
                "scenario_hash": content_hash(recipe),
                "scenario_source_manifest_hash": scenario["manifest_hash"] if scenario else None}
    return {
        "schema_version": "faultlab-native-agent-run/v1", "status": status, "complete": complete,
        "mode": "healthy" if healthy else "regression", "evidence_class": "NATIVE_AGENT_CONFORMANCE",
        "agent": snapshot.descriptor, "execution_identity": identity,
        "execution_identity_hash": content_hash(identity), "scenario_source": scenario,
        "configuration_hash": campaign.configuration_hash, "campaign_id": campaign.campaign_id,
        "legacy_source_mode": "offline_fixture",
        "legacy_source_mode_meaning": "Native orchestration with a declared deterministic model double",
        "responding_model": model_identity(),
        "managed_provider_calls": 0, "managed_provider_spend_dollars": 0.0,
        "external_provider_calls": None, "external_spend_dollars": None,
        "model_double_calls": provider.calls,
        "usage_note": "Legacy model-call counters count deterministic double calls. Arbitrary user-code activity and spending are unmetered.",
        "recipe": recipe.model_dump(mode="json"), "required_trials": required, "trial_count": len(trials),
        "trials": trials, "failed_checks": sorted({check for row in trials for check in row["failed_checks"]}),
        "execution": execution.model_dump(mode="json") if execution else None,
        "regression_assertions": (coordinator.store.get_record("regression_assertions", execution.execution_id)
                                  if execution else None),
        "error_type": type(error).__name__ if error else None,
        "paths": {"output_dir": str(output), "summary": str(output / "summary.json"),
                  "report": str(output / "report.html"), "portable": None,
                  "agent_snapshot": str(snapshot.path)},
        "limitations": [
            "Native smolagents orchestration under a declared adapter and deterministic model double; not production-model behavior.",
            "The user-owned constructor and tool wrappers are trusted code; process separation is not an operating-system security sandbox.",
            "Only the pinned framework and synthetic orders task are supported.",
            "Managed provider calls are zero; arbitrary user-code activity and spending are unmetered.",
            "This conformance result establishes neither generated repair, ACCEPTED policy, nor independent customer adoption.",
        ],
    }


async def run_native_agent(output_dir, agent_path, *, bundle_dir=None, healthy=False,
                           turn_timeout_seconds=10.0):
    """Select trusted constructor code explicitly; scenario bundles remain data."""
    if type(turn_timeout_seconds) not in (int, float) or not 0 < turn_timeout_seconds <= 20:
        raise ValueError("The native request deadline must be in (0, 20] seconds")
    source = read_agent(agent_path)
    if healthy and bundle_dir is not None:
        raise ValueError("Healthy control does not consume a fault bundle")
    if not healthy and bundle_dir is None:
        raise ValueError("Select an explicit portable regression bundle")
    imported = _inspect_offline_bundle(bundle_dir) if bundle_dir is not None else None
    scenario = inspect_example_bundle(imported[0]) if imported else None
    if imported and scenario["manifest_hash"] != imported[1].bundle.manifest_hash:
        raise ValueError("Scenario changed during validation")
    output = _new_output(output_dir)
    snapshot = source.freeze(output)
    portable = _portable_copy(imported[0], output, scenario["manifest_hash"]) if imported else None
    if portable:
        imported = _inspect_offline_bundle(portable / "bundle")
    recipe = FaultSpec(seed=105, primitives=[]) if healthy else rejection_recipe()
    required, execution, error = (1 if healthy else 3), None, None
    async with _environment(output, snapshot, turn_timeout_seconds, recipe, scenario, required) as (coordinator, campaign, runner, provider):
        ledger = CampaignLedger(coordinator.store, campaign.campaign_id, campaign.caps)
        policy = coordinator.policies.baseline()
        try:
            if healthy:
                await runner.run(campaign, recipe, policy, ledger=ledger)
            else:
                directory, inspected = imported
                registry = AgentRegistry(coordinator.store)
                binding = coordinator.store.get_record("campaign_registrations", campaign.campaign_id)
                configuration = coordinator.store.get_record("configurations", campaign.configuration_hash)
                execution_id = new_id("execution")

                async def fresh(selected_recipe, registration, transferred, index, *, fixture_id):
                    trial = await runner.run(campaign, selected_recipe, transferred, purpose="reproduction",
                        trial_index=index, fixture_id=fixture_id, ledger=ledger,
                        agent_registration_id=registration.registration_id,
                        study_id=execution_id, evidence_context_id=execution_id)
                    record = provider.records.get(trial.episode_id)
                    if trial.lifecycle == "COMPLETED" and not valid_execution(record, snapshot, provider.identity):
                        raise ValueError("Incomplete native execution")
                    return trial

                execution = await RegressionRunner(coordinator.store, registry).execute(
                    directory, configuration, binding["registration_id"], explicit_fresh=True,
                    profile_id="sandbox-v1", run_fresh=fresh, policy_version=policy, execution_id=execution_id)
        except Exception as caught:
            error = caught
        result = _summarize(output, snapshot, coordinator, campaign, provider, recipe,
                            required, healthy, scenario, execution, error)
        if portable is not None:
            result["paths"]["portable"] = str(portable)
        _write_json(output / "summary.json", result)
        write_report(result)
        return result
