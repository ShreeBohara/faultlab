"""Run an explicitly selected local decision agent through the existing orders harness.

The legacy registry identifies the trusted Actor/broker implementation. A separate
execution identity binds the user-authored decision source to each fresh trial.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
import secrets
import shutil

import httpx

from app.adapters.business_tools import WorldClient
from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, content_hash, new_id
from app.examples.rejected_upgrade import (
    REQUEST_MODEL, SIDECAR_NAME, _inspect_offline_bundle, _new_output,
    _trial_evidence, _write_json, inspect_example_bundle, rejection_recipe,
)
from app.examples.simulator import create_app
from app.integrations.registry import AgentRegistry
from app.integrations.regression_runner import RegressionRunner
from app.lab.budgets import CampaignLedger
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.local_agents.source import read_agent
from app.local_agents.transport import LocalAgentProvider
from app.local_agents.report import write_report


PROTOCOL = "faultlab-local-action/v1"
TASK_TEXT = "Upgrade this order to express and send one truthful confirmation."


def _valid_process(record, source_hash):
    if not isinstance(record, dict):
        return False
    requests = record.get("requests")
    count = record.get("request_count")
    return (isinstance(requests, list) and type(count) is int and 1 <= count <= 8
            and len(requests) == count
            and all(isinstance(row, dict) and isinstance(row.get("request_id"), str)
                    and row.get("delivery_status") == "RETURNED_TO_ACTOR"
                    for row in requests)
            and len({row.get("request_id") for row in requests}) == count
            and isinstance(requests[-1].get("validated_action"), dict)
            and (requests[-1].get("validated_action") or {}).get("kind") == "report"
            and type(record.get("exit_code")) is int and record["exit_code"] == 0
            and type(record.get("process_id")) is int and record["process_id"] > 0
            and record.get("source_hash") == source_hash
            and record.get("protocol_status") == "COMPLETED"
            and record.get("report_completed") is True
            and record.get("process_creation_complete") is True
            and record.get("cleanup_complete") is True
            and record.get("errors") == [])


class _LocalRunner(EpisodeRunner):
    async def run(self, *args, **kwargs):
        if kwargs.get("source_mode", "offline_fixture") != "offline_fixture":
            raise ValueError("Local decision runs use the declared non-live harness")
        episode_id = kwargs.get("episode_id") or new_id("episode")
        try:
            async with self.provider.episode(episode_id):
                return await super().run(*args, **{**kwargs, "episode_id": episode_id,
                                                  "source_mode": "offline_fixture"})
        finally:
            record = self.provider.records.get(episode_id)
            if record is not None:
                value = {**record, "episode_id": episode_id}
                self.store.put_record("local_agent_executions", episode_id, value, immutable=True)
                self.store.append_event(episode_id, type="local_agent_execution", payload=value)


@asynccontextmanager
async def _environment(output, snapshot, turn_timeout_seconds, recipe, scenario):
    settings = Settings(wandb_model=REQUEST_MODEL, faultlab_artifact_dir=str(output / "state"))
    control = secrets.token_urlsafe(32)
    simulator = create_app(database_dir=output / "worlds", control_token=control, settings=settings)
    coordinator = LabCoordinator(settings)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                                    base_url="http://127.0.0.1:8001", trust_env=False) as client:
            provider = LocalAgentProvider(snapshot, output / "agent-work",
                                          turn_timeout_seconds=turn_timeout_seconds)
            world = WorldClient("http://127.0.0.1:8001", control, client=client)
            runner = _LocalRunner(coordinator.store, world, provider, offline_fixture=True)
            coordinator.runner = runner
            # This is only the existing Actor request/tokenizer contract. The
            # public result never claims that this model generated an answer.
            campaign = coordinator.create(CampaignRequest(mode="baseline", config_profile_id="live-v1",
                task_text=TASK_TEXT, order_id="order-local-agent"))
            identity = {"agent": snapshot.descriptor, "configuration_hash": campaign.configuration_hash,
                        "decision_runtime": provider.identity,
                        "scenario_hash": content_hash(recipe),
                        "scenario_source_manifest_hash": scenario["manifest_hash"] if scenario else None,
                        "protocol": PROTOCOL, "turn_timeout_seconds": turn_timeout_seconds,
                        "decision_source": "explicit_local_python_file",
                        "request_profile_meaning": "Actor formatting and tokenizer only; no responding model"}
            coordinator.store.put_record("local_agent_plans", campaign.campaign_id, identity, immutable=True)
            yield coordinator, campaign, runner, provider, identity
    finally:
        await coordinator.close()


def _portable_copy(directory, output, expected_manifest_hash):
    """Copy only the validated scenario and installed test; never copy user code."""
    portable = output / "portable"
    portable.mkdir()
    shutil.copytree(directory, portable / "bundle", symlinks=True)
    shutil.copy2(directory.parent / SIDECAR_NAME, portable / SIDECAR_NAME, follow_symlinks=False)
    # Refuse a changed input, symlink or incomplete copy before publishing a
    # portable path. Data never supplies the executable behavioral test.
    _, copied = _inspect_offline_bundle(portable / "bundle")
    if copied.bundle.manifest_hash != expected_manifest_hash:
        raise ValueError("Scenario changed while snapshotting the portable regression")
    template = Path(__file__).with_name("test_local_agent.py.txt")
    (portable / "test_local_agent.py").write_bytes(template.read_bytes())
    return portable


def _summarize(output, snapshot, coordinator, campaign, provider, identity,
               recipe, required, healthy, scenario, execution, error):
    trials = []
    for episode in coordinator.store.list_campaign_episodes(campaign.campaign_id):
        row = _trial_evidence(coordinator.store, episode["episode_id"], recipe)
        process = coordinator.store.get_record("local_agent_executions", episode["episode_id"])
        row["local_agent_execution"] = process
        if (not _valid_process(process, snapshot.source_hash)
                or process.get("episode_id") != episode["episode_id"]
                or process.get("identity") != identity["decision_runtime"]):
            row["evidence_valid"] = False
            row["status"] = "INCOMPLETE"
            row["evidence_issues"].append("LOCAL_AGENT_EXECUTION_INCOMPLETE")
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
    return {
        "schema_version": "faultlab-local-agent-run/v1", "status": status, "complete": complete,
        "mode": "healthy" if healthy else "regression", "evidence_class": "LOCAL_AGENT_REGRESSION",
        "agent": snapshot.descriptor, "execution_identity": identity,
        "execution_identity_hash": content_hash(identity), "scenario_source": scenario,
        "configuration_hash": campaign.configuration_hash, "campaign_id": campaign.campaign_id,
        "legacy_source_mode": "offline_fixture",
        "legacy_source_mode_meaning": "Non-live orders harness; decisions come from the explicitly selected local program",
        "responding_model": None, "managed_provider_calls": 0, "managed_provider_spend_dollars": 0.0,
        "external_provider_calls": None, "external_spend_dollars": None,
        "decision_calls": provider.calls,
        "usage_note": "Legacy actor/model-call counters count local decisions. External program activity and spending are not metered.",
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
            "Trusted local Python decision logic under FaultLab's orders Actor protocol; not an unchanged native framework agent.",
            "The child process and Python audit guards are not an operating-system security sandbox.",
            "FaultLab makes no provider calls here; arbitrary local program activity and external spending are unobserved.",
            "The legacy registry identifies the trusted execution harness, separately from this run's decision-source identity.",
            "This synthetic regression does not establish a generated repair, accepted policy or live-model reliability.",
        ],
    }


async def run_local_agent(output_dir, agent_path, *, bundle_dir=None, healthy=False,
                          turn_timeout_seconds=10.0):
    """Run three fresh regression trials, or one no-fault task-completion control.

The operator must explicitly select the Python source. Bundle contents cannot
select code. Source validation never imports or executes the selected program.
    """
    if type(turn_timeout_seconds) not in (int, float) or not 0 < turn_timeout_seconds <= 20:
        raise ValueError("The local decision deadline must be in (0, 20] seconds")
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
    # Execute the validated local snapshot, never reread a movable source path
    # after the first trial. The scenario, execution and export share one pin.
    portable = _portable_copy(imported[0], output, scenario["manifest_hash"]) if imported else None
    if portable:
        imported = _inspect_offline_bundle(portable / "bundle")
    recipe = FaultSpec(seed=105, primitives=[]) if healthy else rejection_recipe()
    execution = None
    error = None
    async with _environment(output, snapshot, turn_timeout_seconds, recipe, scenario) as (coordinator, campaign, runner, provider, identity):
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
                    process = provider.records.get(trial.episode_id)
                    if trial.lifecycle == "COMPLETED" and not _valid_process(process, snapshot.source_hash):
                        # The saved attempt remains available. A deadline or
                        # cleanup failure cannot trigger another agent attempt.
                        raise ValueError("Incomplete local decision execution")
                    return trial

                execution = await RegressionRunner(coordinator.store, registry).execute(
                    directory, configuration, binding["registration_id"], explicit_fresh=True,
                    profile_id="sandbox-v1", run_fresh=fresh, policy_version=policy, execution_id=execution_id)
        except Exception as caught:
            error = caught
        result = _summarize(output, snapshot, coordinator, campaign, provider, identity, recipe,
                            1 if healthy else 3, healthy, scenario, execution, error)
        if portable is not None:
            result["paths"]["portable"] = str(portable)
        _write_json(output / "summary.json", result)
        write_report(result)
        return result
