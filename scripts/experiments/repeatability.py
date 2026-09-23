#!/usr/bin/env python3
"""Fixed public-case repeatability study; dry planning is the default.

Run from the repository with .venv/bin/python. The backend must be stopped,
while the simulator stays running. This process reserves localhost:8000 for its
lifetime to prevent starting a second dashboard scheduler over the experiment.
Use a new --output directory for every explicit run; uncertain effects are never
resumed or replayed. This measures the unchanged reference Actor across fresh identities, not a repair.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import signal
import socket
import sys

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.contracts.models import Campaign, CampaignBudget, EpisodeBudget, FaultSpec, Provenance, canonical_json, content_hash, new_id, utc_now
from app.integrations.registry import AgentRegistry
from app.lab.baseline_study import summarize
from app.lab.budgets import CampaignLedger, protected_reservations
from app.lab.configuration import frozen_configuration, source_provenance
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceContext
from app.lab.exports import development_recording
from app.lab.reproduction import valid_trial
from app.lab.storage import LabStore
from app.referee.manifests import load_manifest
from app.telemetry.safety import public_json


REPEATS = 10
TASK = "Upgrade the authorized order to express shipping, then record one truthful confirmation."


class PlanningError(ValueError):
    """Only locally authored non-secret messages may be printed to the terminal."""


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New separate results directory; existing runs are never resumed")
    parser.add_argument("--allowance-dollars", type=float, required=True, help="Explicit available allowance, positive and at most $500")
    parser.add_argument("--order-id", default="order-1")
    parser.add_argument("--confirm-entity", default="shreetbohara-quinstreet")
    parser.add_argument("--project", default="Faultlab")
    parser.add_argument("--execute-live", action="store_true")
    return parser.parse_args(argv)


def reviewed_cases():
    # Public Phase 1 retained recipes, fixed before this study. The follow-up's
    # source was 12 ticks; its exported reduced incident is exactly 4 ticks.
    # No private promotion, final-audit or portability manifest is read here.
    development = load_manifest("development")
    healthy = next(case for case in development["cases"] if case["case_id"] == "dev-1")
    if healthy["fixture_id"] != "standard-v1" or healthy["fault_spec"]["primitives"]:
        raise PlanningError("Reviewed healthy development control changed")
    cases = [{**healthy, "case_id": "healthy", "source_manifest_hash": development["manifest_hash"]}]
    for name, ticks, seed, recipe_hash, manifest_hash, episode in (
        ("delay-5", 5, 19, "d07dea93a884f59fdb035a37f80e93dbf36b1686fc8d78c199eaebd6c938249d",
         "adfa165aca81795de8b5eba4edc9fb63df93e71123c2c42151052d6adc6f6cc0", "episode-12815b0d18394796af96f6c9531f44a9"),
        ("delay-4", 4, 20240517, "0a610483d53a4e5fb8ef022a0b73bb947036dd9a0572982a2c29eaf7c3e650fe",
         "41a598e99d056468f37af08fe6bb146ba73d331e84c149310fcfb722c26f9c21", "episode-a2a7ab23c443411aabb20e1a92641410"),
    ):
        recipe = FaultSpec.model_validate({"seed": seed, "primitives": [{"target_tool": "update_order",
            "target_service": "orders", "occurrence": 1, "kind": "F2", "parameters": {
                "completion_delay_ticks": ticks, "terminal_status": "SUCCEEDED", "failure_code": None}}]}).model_dump(mode="json")
        if content_hash(recipe) != recipe_hash:
            raise PlanningError("Reviewed retained delay recipe changed")
        cases.append({"case_id": name, "fixture_id": "standard-v1", "expected_version": 1,
            "fault_spec": recipe, "source_recipe_hash": recipe_hash, "source_manifest_hash": manifest_hash,
            "source_episode_id": episode, "target_invariant": "C5"})
    return cases


def execution_settings(base, args):
    return replace(base, faultlab_aria_publish_enabled=False,
        faultlab_confirmed_entity=args.confirm_entity,
        faultlab_artifact_dir=str(args.output.resolve()), faultlab_dollar_cap=args.allowance_dollars)


def prepare(args):
    if not math.isfinite(args.allowance_dollars) or not 0 < args.allowance_dollars <= 500:
        raise PlanningError("Explicit allowance must be positive, at most $500 and within remaining authorization")
    if args.output.exists():
        raise PlanningError("A new output directory is required; saved trials cannot be overwritten or resumed")
    # Dry planning reads exported settings only. It never reads .env, resolves a
    # control token, contacts a service, creates a registration or writes files.
    settings = execution_settings(Settings.from_env(env_path="/dev/null"), args)
    if not all(settings.role_models.values()) or settings.model_call_dollar_bounds is None:
        raise PlanningError("Export reviewed role models and verified price settings before planning")
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap,
        tokens=settings.faultlab_token_cap, dollars=args.allowance_dollars)
    cases = reviewed_cases()
    target = frozen_configuration(settings, caps, "live-v1")
    # Validate the order ID and task with the actual campaign contract offline.
    Campaign(campaign_id="campaign-plan", mode="baseline", task_text=TASK, order_id=args.order_id,
        config_profile_id="live-v1", model=settings.wandb_model, configuration_hash=content_hash(target), caps=caps)
    slots = [{"case_id": case["case_id"], "fixture_id": case["fixture_id"],
        "scenario_hash": content_hash(case["fault_spec"]), "repeat_index": repeat,
        "block_index": repeat // 3, "trial_index": repeat % 3,
        "episode_id": new_id("episode"), "status": "NOT_ATTEMPTED"}
        for repeat in range(REPEATS) for case in cases]
    calls = len(slots) * EpisodeBudget().actor_calls
    protected = protected_reservations(caps)
    all_calls = calls + sum(row["calls"] for row in protected.values())
    per_call_tokens = caps.input_tokens_per_call + caps.output_tokens_per_call
    maximum_bound = settings.model_call_dollar_bound
    plan = {"schema_version": "faultlab-repeatability-plan/v1", "experiment": "public_repeatability_baseline",
        "accepted_policy_transfer": False, "source_mode": "live", "model": settings.wandb_model,
        "models": settings.role_models, "harness_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "case_manifest_hash": content_hash(cases), "cases": cases, "configuration_hash": content_hash(target),
        "task_text": TASK, "order_id": args.order_id, "policy_version": "policy-v0", "arm": "B0",
        "repeats_per_case": REPEATS, "trial_order": "repeat_then_case_fixed_round_robin",
        "planned_trials": len(slots), "planned_model_call_ceiling": calls,
        "planned_token_ceiling": calls * per_call_tokens,
        "planned_actor_dollar_ceiling": round(calls * settings.model_call_dollar_bounds["actor"], 8),
        "batch_admission_max_role_dollar_reservation": round(calls * maximum_bound, 8),
        "allowance_dollars": args.allowance_dollars, "existing_protected_reservations": protected,
        "minimum_allowance_with_protected_reserves": round(all_calls * maximum_bound, 8),
        "minimum_call_cap_with_protected_reserves": all_calls,
        "minimum_token_cap_with_protected_reserves": all_calls * per_call_tokens,
        "pricing": target["pricing"], "model_settings": target["model_settings"],
        "slots": slots, "output_directory": str(args.output.resolve()),
        "limits": ["Three public development cases, ten predeclared fresh-world trials each; no learned policy.",
            "Fresh UUIDs are preserved; no seed or identity override. This measures combined fresh-identity and provider variation.",
            "repeat_index is the study index; block_index/trial_index retain the existing three-slot schema without rerunning qualification gates.",
            "No retry or replacement of any attempted, invalid, interrupted or unfavorable trial.",
            "Stop on infrastructure, untriggered scheduled fault, configuration change or unverified episode evidence; preserve every planned slot.",
            "Completion, fixed-check outcomes, original report availability and Weave verification are separate measures.",
            "Protected evaluation suites are not read or executed by this study."]}
    if all_calls > caps.model_calls or all_calls * per_call_tokens > caps.tokens:
        raise PlanningError("Complete study and existing protected reserves exceed frozen call or token cap")
    if all_calls * maximum_bound > args.allowance_dollars:
        raise PlanningError(f"Complete study and protected reserves require at least ${plan['minimum_allowance_with_protected_reserves']:.5f}")
    return settings, caps, cases, target, plan


def verify_frozen(settings, caps, cases, target, plan, registry, registration_id):
    if content_hash(frozen_configuration(settings, caps, "live-v1")) != plan["configuration_hash"]:
        raise PlanningError("Frozen runtime or model configuration changed during execution")
    if content_hash(reviewed_cases()) != plan["case_manifest_hash"] or content_hash(cases) != plan["case_manifest_hash"]:
        raise PlanningError("Frozen case definitions changed during execution")
    if sha256(Path(__file__).read_bytes()).hexdigest() != plan["harness_sha256"]:
        raise PlanningError("Experiment harness changed during execution")
    registry.verify(registration_id, target)


def write_json(path, value, secrets=()):
    value = public_json(json.loads(canonical_json(value)), secrets=secrets, max_bytes=64 * 1024 * 1024)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


async def execute(args, caps, case_list, target, plan):
    # Acquiring this port fails if the dashboard backend is active; keeping the
    # socket bound prevents it starting a competing scheduler during this batch.
    guard = socket.socket()
    try:
        guard.bind(("127.0.0.1", 8000))
    except OSError:
        guard.close()
        raise PlanningError("Stop the backend on localhost:8000 before this standalone experiment; keep the simulator running") from None
    store = coordinator = runner = ledger = session = None
    record = None
    stop_requested = False
    loop = asyncio.get_running_loop()
    def request_stop():
        nonlocal stop_requested
        stop_requested = True
    try:
        # This is the only credential read and occurs after --execute-live.
        base_settings = Settings.from_env()
        # A separate result store still talks to the existing local simulator.
        # Resolve its capability before changing the artifact directory; the
        # default capability file belongs to that original service directory.
        base_settings = replace(base_settings, faultlab_control_token=base_settings.local_control_token())
        settings = execution_settings(base_settings, args)
        settings.require_live()
        if settings.project_path != f"{args.confirm_entity}/{args.project}":
            raise PlanningError("Configured W&B project differs from the explicitly confirmed destination")
        if content_hash(frozen_configuration(settings, caps, "live-v1")) != plan["configuration_hash"]:
            raise PlanningError("Configuration changed after dry planning")
        args.output.mkdir(parents=True, exist_ok=False)
        secrets = (settings.wandb_api_key, settings.typesafe_api_key, settings.faultlab_control_token)
        # Preserve the whole intended inventory even if readiness fails before
        # a campaign or any provider request is created.
        write_json(args.output / "plan.json", plan, secrets)
        store = LabStore(args.output / "lab.sqlite3")
        coordinator = LabCoordinator(settings, store=store)
        await coordinator.require_simulator()
        registry = AgentRegistry(store)
        registration = registry.register_reference(target)
        campaign = Campaign(campaign_id=new_id("campaign"), mode="baseline", task_text=TASK,
            order_id=args.order_id, config_profile_id="live-v1", model=settings.wandb_model,
            configuration_hash=registration.configuration_hash, caps=caps, state="RUNNING", execution_epoch=1)
        coordinator.save(campaign)
        coordinator.active_id = campaign.campaign_id
        store.put_record("campaign_registrations", campaign.campaign_id, {"registration_id": registration.registration_id}, immutable=True)
        store.put_record("campaign_provenance", campaign.campaign_id, {**source_provenance(),
            "experiment": "public_repeatability_baseline", "harness_sha256": plan["harness_sha256"],
            "aria_publication_enabled": False}, immutable=True)
        baseline = coordinator.policies.baseline()
        if baseline.decision != "BASELINE" or baseline.content.rules:
            raise PlanningError("Repeatability baseline requires the unchanged empty policy")
        ledger = CampaignLedger(store, campaign.campaign_id, caps, dollar_bounds=settings.model_call_dollar_bounds)
        coordinator.ledgers[campaign.campaign_id] = ledger
        study_id = new_id("repeatability")
        reservation = "repeatability:" + study_id
        ledger.reserve(reservation, plan["planned_model_call_ceiling"])
        record = {**plan, "study_id": study_id, "campaign_id": campaign.campaign_id,
            "registration_id": registration.registration_id, "policy_hash": baseline.policy_hash,
            "status": "RUNNING", "started_at": utc_now().isoformat(), "trials": [],
            "evidence": {}, "evaluation": {"status": "not_started"}, "failures": [], "by_case": {}}
        trials = []
        def persist():
            record["summary"] = summarize(trials)
            record["by_case"] = {case["case_id"]: summarize([trial for trial in trials
                if trial.episode_id in {slot["episode_id"] for slot in record["slots"] if slot["case_id"] == case["case_id"]}]) for case in case_list}
            budget = store.get_record("budgets", campaign.campaign_id)
            record["accounting"] = {"charged_model_calls": budget["used_calls"],
                "charged_token_upper_bound": budget["charged_token_upper_bound"],
                "charged_dollar_upper_bound": budget["charged_dollar_upper_bound"],
                "measured_input_tokens": budget["measured_input_tokens"],
                "measured_output_tokens": budget["measured_output_tokens"],
                "usage_metadata_known": budget["usage_metadata_known"],
                "unknown_token_calls": budget["unknown_token_calls"],
                "measured_token_price_estimate": (budget["measured_input_tokens"] * settings.model_rates_for_role("actor")[0]
                    + budget["measured_output_tokens"] * settings.model_rates_for_role("actor")[1]) / 1_000_000,
                "price_estimate_complete": budget["usage_metadata_known"],
                "actual_provider_cost_dollars": budget["actual_cost_dollars"]}
            store.put_record("repeatability_studies", study_id, record)
            write_json(args.output / "summary.json", record, secrets)
        persist()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, request_stop)
        try:
            runner, _ = await coordinator._get_runner(True)
            actor = registry.reviewed_actor(registration.registration_id, model_id=settings.wandb_model)
            provenance = Provenance(campaign_id=campaign.campaign_id, episode_id=study_id,
                origin="prototype", split="development", arm="B0", source_mode="live",
                experiment_purpose="discovery", trial_index=0, study_id=study_id,
                evidence_context_id=study_id, execution_epoch=campaign.execution_epoch,
                agent_registration_id=registration.registration_id)
            metadata = {**provenance.model_dump(mode="json"), "model_id": settings.wandb_model,
                "policy_hash": baseline.policy_hash, "contract_hash": target["contract_hash"],
                "scorer_hash": target["scorer_hash"]}
            session = await coordinator.evaluation_publisher.begin(study_id, metadata,
                expected_episode_ids=[slot["episode_id"] for slot in record["slots"]], frozen=False)
            record["evaluation"] = {"status": "pending", "batch_id": study_id}
            cases = {case["case_id"]: case for case in case_list}
            for slot in record["slots"]:
                if stop_requested:
                    break
                verify_frozen(settings, caps, case_list, target, plan, registry, registration.registration_id)
                case = cases[slot["case_id"]]
                slot["status"] = "RUNNING"
                persist()
                trial = await runner.run(campaign, FaultSpec.model_validate(case["fault_spec"]), baseline,
                    episode_id=slot["episode_id"], purpose="discovery", arm="B0", trial_index=slot["trial_index"],
                    fixture_id=slot["fixture_id"], study_id=study_id, evidence_context_id=study_id,
                    ledger=ledger, reservation=reservation, stop=lambda: stop_requested,
                    source_mode="live", agent_registration_id=registration.registration_id, actor=actor)
                trials.append(trial)
                record["trials"].append(trial.model_dump(mode="json"))
                slot["status"] = trial.lifecycle
                campaign.latest_episode_id = trial.episode_id
                coordinator.save(campaign)
                persisted = store.get_record("episodes", trial.episode_id)
                slot["world_id"] = trial.world_id
                slot["outcome"] = trial.outcome
                slot["failed_checks"] = trial.failed_checks
                slot["original_report_present"] = persisted.get("report") is not None
                try:
                    if persisted.get("verdict"):
                        await session.record_prediction(trial.episode_id,
                            inputs={"case_id": slot["case_id"], "repeat_index": slot["repeat_index"], "block_index": slot["block_index"], "trial_index": slot["trial_index"], "scenario_hash": trial.scenario_hash, "arm": "B0", "source_mode": "live"},
                            original_report=persisted["report"],
                            persisted_scores={check["check_id"]: check["passed"] for check in persisted["verdict"]["checks"]})
                    if trial.lifecycle == "COMPLETED":
                        evidence = await coordinator.evidence_gateway.get(trial.episode_id,
                            EvidenceContext(campaign.campaign_id, study_id, study_id), stopped=lambda: stop_requested)
                        record["evidence"][trial.episode_id] = {"status": evidence.source, "root_call_id": evidence.root_call_id}
                    else:
                        record["evidence"][trial.episode_id] = {"status": "ineligible_lifecycle", "lifecycle": trial.lifecycle}
                except Exception as error:
                    record["evidence"][trial.episode_id] = {"status": "weave_pending", "error_type": type(error).__name__,
                        "ingestion": store.get_record("ingestions", trial.episode_id)}
                persist()
                print(json.dumps({"study_id": study_id, "attempted": len(trials), "case_id": slot["case_id"],
                    "outcome": trial.outcome, "evidence": record["evidence"].get(trial.episode_id),
                    "accounting": record["accounting"]}), flush=True)
                if not valid_trial(trial) or record["evidence"][trial.episode_id]["status"] != "weave_verified":
                    record["failures"].append({"episode_id": trial.episode_id, "message": "Trial validity or evidence barrier failed; remaining slots are not attempted"})
                    break
            record["status"] = "COMPLETED" if len(trials) == plan["planned_trials"] and all(valid_trial(trial) for trial in trials) else "INCOMPLETE"
            if len(trials) == plan["planned_trials"]:
                record["evaluation"] = await session.finish(summarize(trials))
        except Exception as error:
            record["status"] = "INCOMPLETE"
            for slot in record["slots"]:
                if slot["status"] == "RUNNING":
                    slot["status"] = "ATTEMPT_ERROR"
            record["failures"].append({"error_type": type(error).__name__, "message": "Execution or evidence failed; all attempted effects are retained without retry"})
        finally:
            ledger.release(reservation)
            record["ended_at"] = utc_now().isoformat()
            record["stop_requested"] = stop_requested
            campaign.state = "STOPPED" if stop_requested else "COMPLETED" if record["status"] == "COMPLETED" else "ERROR"
            campaign.stop_requested = stop_requested
            campaign.telemetry_status = "weave_verified" if len(record["evidence"]) == plan["planned_trials"] and all(v["status"] == "weave_verified" for v in record["evidence"].values()) else "weave_pending"
            campaign.terminal_reason = "Public repeatability baseline; all predeclared outcomes retained; no repair or transfer claim"
            coordinator.save(campaign)
            coordinator.active_id = None
            persist()
            write_json(args.output / "recording.json", development_recording(store, campaign.campaign_id, secrets=secrets), secrets)
            write_json(args.output / "telemetry.json", {kind: store.list_records(kind) for kind in (
                "trace_registrations", "ingestions", "evidence", "telemetry_outbox", "telemetry_evaluations",
                "telemetry_predictions", "telemetry_summaries")}, secrets)
        print(json.dumps({"study_id": study_id, "status": record["status"],
            "summary_file": str((args.output / "summary.json").resolve()),
            "accounting": record["accounting"], "evaluation": record["evaluation"],
            "verified_episode_count": sum(value["status"] == "weave_verified" for value in record["evidence"].values())}), flush=True)
        return 0 if record["status"] == "COMPLETED" and record["evaluation"]["status"] == "weave_verified" and campaign.telemetry_status == "weave_verified" else 1
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        if runner is not None:
            for resource in (runner.world_client, runner.provider, getattr(runner, "telemetry_worker", None)):
                if resource is not None:
                    try:
                        await asyncio.wait_for(resource.close(), timeout=3)
                    except Exception:
                        pass
        if store is not None:
            store.close()
        guard.close()


def main():
    args = arguments()
    try:
        _, caps, cases, target, plan = prepare(args)
        if not args.execute_live:
            print(json.dumps({"dry_run": True, "provider_calls": 0, "registrations_created": 0, **plan}, indent=2))
            return 0
        return asyncio.run(execute(args, caps, cases, target, plan))
    except Exception as error:
        # Only reviewed setup errors are echoed; never print SDK/config contents.
        safe_message = str(error) if isinstance(error, PlanningError) else "Preflight failed; inspect local configuration and simulator readiness"
        print(json.dumps({"status": "REJECTED", "error_type": type(error).__name__, "message": safe_message}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
