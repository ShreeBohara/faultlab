"""Replay: a sealed envelope's recorded inputs in a fresh world, with divergence stop and cut points."""
import asyncio

from faultlab.adapters.reference import ReferenceOrdersAdapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.lab.replay import ReplayAdapter, intent_mapping, rebind, recorded_steps
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=0.0)


def run(coro):
    return asyncio.run(coro)


def record(worker, scenario_id, adapter, attempt_id):
    plan = ORDERS.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=CAPS)
    return run(worker.run(plan, TrialAttempt(attempt_id=attempt_id, plan_hash=plan_hash(plan), lifecycle="READY"), adapter))


def test_rebinding_maps_recorded_identities_and_nothing_else():
    mapping = intent_mapping({"order_id": "order-a", "task_id": "task-a", "expected_version": 1}, {"order_id": "order-b", "task_id": "task-b", "expected_version": 1})
    assert mapping == {"order-a": "order-b", "task-a": "task-b"}
    assert rebind({"x": ["order-a", 1, {"y": "task-a", "z": "other"}]}, mapping) == {"x": ["order-b", 1, {"y": "task-b", "z": "other"}]}


def test_a_replay_in_the_same_scenario_reproduces_the_recorded_run(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())
        recorded = record(worker, "dev-2", ReferenceOrdersAdapter(), "trial-recorded")
        steps = recorded_steps(recorded)
        assert [s["kind"] for s in steps][-1] == "claim" and sum(1 for s in steps if s["kind"] == "call") == len(recorded.source_facts["calls"])
        replay = ReplayAdapter(recorded)
        replayed = record(worker, "dev-2", replay, "trial-replayed")
        assert replay.divergence is None and replay.replayed == len(recorded.source_facts["calls"])
        assert replayed.outcome.execution == "COMPLETED" and replayed.outcome.task == recorded.outcome.task == "COMPLETED"
        assert all(f.result == "PASS" for f in replayed.outcome.findings) and replayed.outcome.claims.mismatches == []
        assert [c["tool"] for c in replayed.source_facts["calls"]] == [c["tool"] for c in recorded.source_facts["calls"]]
        # Identities were rebound: the replayed report cites the new world's evidence, not the recorded ids.
        delivered_here = {e.payload["observation"]["evidence_id"] for e in replayed.events if e.kind == "response_delivered"}
        assert set(replayed.report.original["evidence_ids"]) <= delivered_here
        assert replayed.report.original["evidence_ids"] != recorded.report.original["evidence_ids"]
        assert replayed.outcome.identity.adapter_id == recorded.outcome.identity.adapter_id
        assert replayed.outcome.exposure.all_required_triggered is True


def test_a_replay_in_a_different_world_stops_at_the_first_divergence(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())
        recorded = record(worker, "dev-1", ReferenceOrdersAdapter(), "trial-healthy")
        replay = ReplayAdapter(recorded)
        plan = ORDERS.plan("dev-5", agent=recorded.plan.agent, environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=CAPS)
        diverged = run(worker.run(plan, TrialAttempt(attempt_id="trial-diverged", plan_hash=plan_hash(plan), lifecycle="READY"), replay))
        assert replay.divergence is not None and replay.divergence["tool"] == "update_order"
        assert replay.divergence["recorded"][0]["status"] == "SUCCEEDED" and replay.divergence["delivered"][0]["status"] == "PENDING"
        steps = [e for e in diverged.events if e.kind == "rule_step"]
        assert len(steps) == 1 and steps[0].payload["hook"] == "replay" and steps[0].payload["divergence"]["step"] == replay.divergence["step"]
        assert diverged.report.status == "ABSENT" and diverged.outcome.execution == "COMPLETED"
        assert [c["tool"] for c in diverged.source_facts["calls"]] == ["get_order", "update_order"]


def test_the_replay_command_replays_from_a_bundle_and_from_a_store(tmp_path, capsys):
    import json

    from faultlab import __main__ as cli

    with TrialStore(tmp_path / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())
        record(worker, "dev-1", ReferenceOrdersAdapter(), "trial-a")
        record(worker, "dev-5", ReferenceOrdersAdapter(), "trial-b")
        store.export_bundle(tmp_path / "batch.zip", name="two")
    out = str(tmp_path / "replays.sqlite3")
    assert cli.main(["replay", str(tmp_path / "batch.zip"), "--attempt", "trial-a", "--store", out, "--worlds", str(tmp_path / "w2")]) == 0
    same = json.loads(capsys.readouterr().out)
    assert same["divergence"] is None and same["replayed"]["task"] == "COMPLETED" and same["replayed"]["violations"] == []
    assert cli.main(["replay", str(tmp_path / "trials.sqlite3"), "--attempt", "trial-a", "--scenario", "dev-5", "--store", out,
                     "--worlds", str(tmp_path / "w2")]) == 0
    other = json.loads(capsys.readouterr().out)
    assert other["divergence"]["tool"] == "update_order" and other["replayed"]["reason"] is None
    assert cli.main(["replay", str(tmp_path / "batch.zip"), "--attempt", "trial-b", "--cut-at", "1", "--store", out, "--worlds", str(tmp_path / "w2")]) == 0
    cut = json.loads(capsys.readouterr().out)
    assert cut["steps_replayed"] == 1 and cut["replayed"]["task"] == "CORRECTLY_REFUSED"
    assert cli.main(["replay", str(tmp_path / "batch.zip"), "--store", out]) == 2          # several envelopes, no --attempt
    assert cli.main(["replay", str(tmp_path / "batch.zip"), "--attempt", "nope", "--store", out]) == 2
    capsys.readouterr()


def test_a_cut_point_replay_hands_the_session_to_a_continuation(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())
        recorded = record(worker, "dev-1", ReferenceOrdersAdapter(), "trial-full")

        async def give_up(session):
            i = session.intent
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                    "evidence_ids": [o.evidence_id for o in session.observations],
                    "next_action": {"kind": "CHECK_EXISTING_NOTIFICATION", "operation_id": i["notification_operation_id"]}}

        replay = ReplayAdapter(recorded, cut_at=2, continuation=give_up)
        cut = record(worker, "dev-1", replay, "trial-cut")
        assert replay.replayed == 2 and replay.divergence is None
        assert [c["tool"] for c in cut.source_facts["calls"]] == ["get_order", "update_order"]
        assert cut.outcome.task == "SAFE_UNRESOLVED" and cut.report.original["overall"] == "SAFE_UNRESOLVED"
        assert all(f.result == "PASS" for f in cut.outcome.findings), [(f.property_id, f.note) for f in cut.outcome.findings if f.result != "PASS"]
