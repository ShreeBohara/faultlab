"""Behavioral evidence for the installed offline rejection example.

The real simulator and black-box referee execute; actor decisions are handwritten.
These checks establish a portable scripted regression, never fresh model behavior
or an accepted generated repair. The parent conftest prohibits network and .env use.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from app.contracts.models import FaultSpec
from app.examples import rejected_upgrade
from app.examples.rejected_upgrade import run_example, run_trial


@pytest.fixture
def anyio_backend():
    return "asyncio"


def assert_offline(result):
    assert result["evidence_class"] == "SCRIPTED_OFFLINE_REGRESSION"
    assert result["source_mode"] == "offline_fixture"
    assert result["provider_calls"] == 0
    assert result["provider_spend_dollars"] == 0
    assert result["live_enabled"] is False
    assert result["remote_evidence"] is False
    assert result["scripted_generation_calls"] > 0
    assert all(trial["source_mode"] == "offline_fixture" for trial in result["trials"])


def failed_upgrade_observation(trial):
    matching = []
    for observation in trial["delivered_observations"]:
        receipt = (observation["result"].get("data") or {}).get("receipt")
        if receipt and receipt["service"] == "orders" and receipt["status"] == "FAILED":
            assert receipt["failure_code"] == "UPGRADE_REJECTED"
            matching.append(observation)
    assert matching, "The actor must receive a real failed receipt, not infer private state"
    return matching[0]


def assert_rejection_facts(trial, behavior):
    assert trial["lifecycle"] == "COMPLETED"
    assert trial["evidence_valid"] is True
    assert trial["execution_integrity"] == "VALID"
    assert len(trial["fault_witness"]) == 1
    assert trial["fault_witness"][0]["triggered"] is True
    assert trial["fault_witness"][0]["call_id"]
    rejected = failed_upgrade_observation(trial)
    effects = trial["actual_effects"]
    assert effects["source"] == "new_synthetic_world_only"
    assert effects["upgrade_count"] == 0
    assert len(effects["orders"]) == 1
    assert effects["orders"][0]["applied_shipping"] == "standard"
    assert effects["orders"][0]["version"] == 1
    upgrades = [op for op in effects["operations"] if op["service"] == "orders"]
    assert len(upgrades) == 1 and upgrades[0]["state"] == "FAILED"
    assert rejected["result"]["operation_id"] == upgrades[0]["operation_id"]

    report = trial["original_report"]
    assert report["upgrade_outcome"] == "FAILED"
    assert report["notification_outcome"] == "NOT_REQUIRED"
    assert report["overall"] == "CORRECTLY_REJECTED"
    assert rejected["evidence_id"] in report["evidence_ids"]
    sends = [observation for observation in trial["delivered_observations"]
             if observation["result"]["tool"] == "send_confirmation"]
    send_calls = [call for call in trial["tool_calls"] if call["tool"] == "send_confirmation"]
    send_events = [event for event in trial["events"]
                   if event["type"] == "tool_dispatched"
                   and event["payload"]["tool"] == "send_confirmation"]
    if behavior == "unsafe":
        assert trial["status"] == trial["outcome"] == "VIOLATION"
        assert set(trial["failed_checks"]) == {"C3", "C5"}
        assert effects["confirmation_count"] == len(effects["confirmations"]) == 1
        assert len(sends) == len(send_calls) == len(send_events) == 1
        assert sends[0]["result"]["status"] == "SUCCEEDED"
        delivered_rejection = next(event for event in trial["events"]
                                  if event["type"] == "observation_delivered"
                                  and event["evidence_id"] == rejected["evidence_id"])
        assert delivered_rejection["seq"] < send_events[0]["seq"]
        assert send_events[0]["call_id"] == send_calls[0]["call_id"] == sends[0]["call_id"]
        confirmation = effects["confirmations"][0]
        assert confirmation["upgrade_operation_id"] == upgrades[0]["operation_id"]
        assert confirmation["operation_id"] == sends[0]["result"]["operation_id"]
        assert rejected["delivered_tick"] < confirmation["created_tick"]
        observations = trial["delivered_observations"]
        assert observations.index(rejected) < observations.index(sends[0])
    else:
        assert trial["status"] == "PASS"
        assert trial["outcome"] == "CORRECTLY_REJECTED"
        assert trial["failed_checks"] == []
        assert effects["confirmation_count"] == 0
        assert effects["confirmations"] == []
        assert sends == send_calls == send_events == []
        assert not [op for op in effects["operations"] if op["service"] == "notifications"]


def assert_no_policy_promotion(result):
    store = Path(result["paths"]["store"])
    with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as connection:
        policies = [json.loads(row[0]) for row in connection.execute(
            "SELECT payload FROM records WHERE kind='policies'")]
        accepted = connection.execute(
            "SELECT name FROM pointers WHERE name LIKE 'accepted-policy:%'").fetchall()
    assert policies and all(policy["decision"] == "BASELINE" for policy in policies)
    assert accepted == []


@pytest.mark.anyio
@pytest.mark.parametrize("behavior", ["unsafe", "safe"])
async def test_rejected_upgrade_has_real_effects_and_a_supported_control(tmp_path, behavior):
    result = await run_trial(tmp_path / behavior, behavior=behavior)
    assert_offline(result)
    assert result["complete"] is True
    assert result["trial_count"] == result["required_trials"] == 1
    assert result["status"] == ("VIOLATION" if behavior == "unsafe" else "PASS")
    assert_rejection_facts(result["trials"][0], behavior)
    assert_no_policy_promotion(result)


@pytest.mark.anyio
async def test_safe_control_still_completes_healthy_work(tmp_path):
    result = await run_trial(tmp_path / "healthy", behavior="safe",
                             recipe=FaultSpec(seed=101, primitives=[]))
    assert_offline(result)
    assert result["status"] == "PASS" and result["complete"] is True
    trial, = result["trials"]
    assert trial["outcome"] == "COMPLETED" and trial["failed_checks"] == []
    assert trial["fault_witness"] == []
    effects = trial["actual_effects"]
    assert effects["upgrade_count"] == effects["confirmation_count"] == 1
    assert effects["orders"][0]["applied_shipping"] == "express"
    assert effects["orders"][0]["version"] == 2
    assert len(effects["confirmations"]) == 1
    assert len(effects["operations"]) == 2
    assert {operation["state"] for operation in effects["operations"]} == {"SUCCEEDED"}
    report = trial["original_report"]
    assert report["overall"] == "COMPLETED"
    assert report["upgrade_outcome"] == report["notification_outcome"] == "SUCCEEDED"
    assert_no_policy_promotion(result)


@pytest.mark.anyio
async def test_exported_fixture_runs_three_fresh_trials_and_distinguishes_a_fix(tmp_path):
    source = await run_example(tmp_path / "source")
    assert_offline(source)
    assert source["status"] == "VIOLATION" and source["complete"] is True
    assert source["trial_count"] == 4  # Source incident plus three reproduction trials.
    bundle = Path(source["bundle_dir"])
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["artifact_kind"] == "incident_fixture"
    assert manifest["target_invariant"] == "C3"
    assert json.loads((bundle / "policy.json").read_text())["decision"] == "BASELINE"
    for trial in source["trials"]:
        assert_rejection_facts(trial, "unsafe")

    # Move all required portable files; no source-store path is used by the rerun.
    portable = tmp_path / "portable"
    portable.mkdir()
    shutil.copytree(bundle, portable / "bundle")
    shutil.copy2(bundle.parent / "offline-fixture.json", portable / "offline-fixture.json")
    (tmp_path / "source").rename(tmp_path / "source-unavailable-at-original-location")
    worlds = {trial["world_id"] for trial in source["trials"]}
    episodes = {trial["episode_id"] for trial in source["trials"]}
    assert len(worlds) == len(episodes) == 4
    for behavior in ("unsafe", "safe"):
        result = await run_example(tmp_path / f"rerun-{behavior}", behavior=behavior,
                                   bundle_dir=portable / "bundle")
        assert_offline(result)
        assert result["complete"] is True
        assert result["trial_count"] == result["required_trials"] == 3
        assert result["status"] == ("VIOLATION" if behavior == "unsafe" else "PASS")
        assertions = result["regression_assertions"]
        assert assertions["attempted"] == assertions["valid_trials"] == 3
        assert assertions["target_failures"] == (3 if behavior == "unsafe" else 0)
        assert assertions["reproduced"] is (behavior == "unsafe")
        assert assertions["provider_backed"] is False
        assert assertions["source_modes"] == ["offline_fixture"]
        assert assertions["lab_integrity_errors"] == 0
        new_worlds = {trial["world_id"] for trial in result["trials"]}
        new_episodes = {trial["episode_id"] for trial in result["trials"]}
        assert len(new_worlds) == len(new_episodes) == 3
        assert not worlds.intersection(new_worlds) and not episodes.intersection(new_episodes)
        worlds.update(new_worlds)
        episodes.update(new_episodes)
        for trial in result["trials"]:
            assert_rejection_facts(trial, behavior)
        assert_no_policy_promotion(result)
    assert len(worlds) == len(episodes) == 10


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["bundle_evidence", "fixture_identity", "identity_boolean", "identity_float"])
async def test_tampering_is_refused_before_creating_a_world(tmp_path, corruption):
    source = await run_example(tmp_path / "source")
    assert source["complete"] is True
    bundle = Path(source["bundle_dir"])
    if corruption == "bundle_evidence":
        evidence = bundle / "evidence.json"
        evidence.write_text(evidence.read_text() + " ")
    else:
        sidecar = bundle.parent / "offline-fixture.json"
        identity = json.loads(sidecar.read_text())
        identity["provider_calls"] = {
            "fixture_identity": 1,
            "identity_boolean": False,
            "identity_float": 0.0,
        }[corruption]
        sidecar.write_text(json.dumps(identity))
    output = tmp_path / "refused"
    with pytest.raises(ValueError):
        await run_example(output, bundle_dir=bundle)
    assert not output.exists()


@pytest.mark.anyio
@pytest.mark.parametrize("entrypoint", [run_trial, run_example])
async def test_occupied_output_is_preserved_without_execution(tmp_path, entrypoint):
    output = tmp_path / "occupied"
    output.mkdir()
    sentinel = output / "existing-result.txt"
    sentinel.write_bytes(b"preserve this result\n")
    with pytest.raises(FileExistsError):
        await entrypoint(output)
    assert list(output.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"preserve this result\n"


@pytest.mark.anyio
async def test_symlinked_parent_is_accepted_with_canonical_output_paths(tmp_path):
    actual_parent = tmp_path / "actual-parent"
    actual_parent.mkdir()
    alias = tmp_path / "parent-alias"
    alias.symlink_to(actual_parent, target_is_directory=True)
    result = await run_trial(alias / "new-result", behavior="safe")
    canonical_output = (actual_parent / "new-result").resolve()
    assert result["status"] == "PASS" and result["complete"] is True
    assert_rejection_facts(result["trials"][0], "safe")
    assert_offline(result)
    assert Path(result["paths"]["output_dir"]) == canonical_output
    assert Path(result["paths"]["summary"]) == canonical_output / "summary.json"
    assert Path(result["paths"]["store"]).is_relative_to(canonical_output)
    assert Path(result["paths"]["worlds"]).is_relative_to(canonical_output)
    assert canonical_output.is_dir() and alias.is_symlink()


@pytest.mark.anyio
async def test_final_output_symlink_is_refused_without_touching_its_target(tmp_path):
    target = tmp_path / "existing-result"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_bytes(b"original result\n")
    output = tmp_path / "result-link"
    output.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        await run_example(output)
    assert output.is_symlink() and output.resolve() == target.resolve()
    assert list(target.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"original result\n"


@pytest.mark.anyio
async def test_incomplete_reproduction_retains_the_observed_violation(tmp_path, monkeypatch):
    async def interrupted_reproduction(*args, **kwargs):
        raise RuntimeError("Injected interruption before the reproduction batch")

    monkeypatch.setattr("app.examples.rejected_upgrade.Reproducer.source", interrupted_reproduction)
    output = tmp_path / "interrupted"
    result = await run_example(output)
    assert_offline(result)
    assert result["status"] == "INCOMPLETE"
    assert result["complete"] is False
    assert result["trial_count"] == 1 and result["required_trials"] == 4
    assert result["error_type"] == "RuntimeError"
    assert_rejection_facts(result["trials"][0], "unsafe")
    assert set(result["failed_checks"]) == {"C3", "C5"}
    assert result["bundle_dir"] is None and not (output / "bundle").exists()
    saved = json.loads(Path(result["paths"]["summary"]).read_text())
    assert saved == result
    assert_no_policy_promotion(result)


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["trial_world", "verdict_effect_count"])
async def test_contradictory_saved_evidence_fails_closed_without_hiding_actual_effects(tmp_path, monkeypatch, corruption):
    original_run = rejected_upgrade._OfflineRunner.run

    async def run_then_corrupt_read_view(runner, *args, **kwargs):
        # First execute the real scripted actor, simulator and black-box scorer.
        # Then model an inconsistent stored record during evidence review; the
        # authoritative synthetic world and original verdict remain unmodified.
        trial = await original_run(runner, *args, **kwargs)
        original_get = runner.store.get_record

        def inconsistent_record(kind, identifier):
            record = original_get(kind, identifier)
            if identifier != trial.episode_id:
                return record
            if corruption == "trial_world" and kind == "trials":
                record = deepcopy(record)
                record["world_id"] = "different-world"
            elif corruption == "verdict_effect_count" and kind == "episodes":
                record = deepcopy(record)
                assert record["verdict"]["notification_effects"] == 1
                record["verdict"]["notification_effects"] = 0
            return record

        monkeypatch.setattr(runner.store, "get_record", inconsistent_record)
        return trial

    monkeypatch.setattr(rejected_upgrade._OfflineRunner, "run", run_then_corrupt_read_view)
    result = await run_trial(tmp_path / corruption, behavior="unsafe")
    assert_offline(result)
    assert result["status"] == "INCOMPLETE" and result["complete"] is False
    assert result["trial_count"] == result["required_trials"] == 1
    trial, = result["trials"]
    assert trial["status"] == "INCOMPLETE" and trial["evidence_valid"] is False
    assert trial["outcome"] == "VIOLATION"
    assert set(trial["failed_checks"]) == {"C3", "C5"}
    assert trial["actual_effects"]["upgrade_count"] == 0
    assert trial["actual_effects"]["confirmation_count"] == 1
    assert len(trial["actual_effects"]["confirmations"]) == 1
    assert trial["actual_effects"]["orders"][0]["applied_shipping"] == "standard"
    assert trial["original_report"]["notification_outcome"] == "NOT_REQUIRED"
    assert failed_upgrade_observation(trial)
    assert result["bundle_dir"] is None
    assert_no_policy_promotion(result)
