"""Legacy (v1) episodes project into sealed v2 envelopes; nothing is re-scored or invented."""
import json
import os
from pathlib import Path

import pytest

from app.contracts.models import (CheckResult, EpisodeBudget, Episode, Event, FaultExecution, FaultSpec, OperationJournal,
                                  PublicObservation, TaskIntent, TaskReport, ToolCallRecord, ToolResult, TrialResult,
                                  Usage, Verdict, canonical_json, content_hash, utc_now)
from app.lab.storage import LabStore
from faultlab.core import IntegrityError
from faultlab.evidence import validate_structure
from faultlab.evidence import legacy
from faultlab.evidence.legacy import LegacyStore, load_episode_facts, project_episode, project_store

DIGEST_A, DIGEST_B = "a" * 64, "b" * 64


def _configuration():
    return {"schema_version": "faultlab/v1", "model": "deepseek-ai/DeepSeek-V3.1",
            "models": {"actor": "deepseek-ai/DeepSeek-V3.1", "explorer": "m", "mechanic": "m"},
            "model_settings": {"max_output_tokens": 2000, "temperature": 0}, "scorer_hash": DIGEST_A,
            "service_hash": DIGEST_B, "actor_prompt_hash": "c" * 64, "adapter_hash": "d" * 64,
            "episode_budget": EpisodeBudget().model_dump(mode="json")}


def _checks(failed=()):
    return [CheckResult(check_id=f"C{i}", passed=f"C{i}" not in failed, category="x",
                        evidence_ids=["ev-2"] if f"C{i}" in failed else []) for i in range(1, 9)]


def write_legacy_store(path, *, episode_id="episode-1", lifecycle="COMPLETED", with_verdict=True, with_report=True):
    """A small but shape-exact v1 store: every record validates against the legacy contracts."""
    store = LabStore(path)
    config = _configuration()
    config_hash = content_hash(config)
    intent = TaskIntent(task_id="task-1", order_id="order-1", expected_version=1, upgrade_operation_id="op-up",
                        notification_operation_id="op-note", upgrade_idempotency_key="key-up",
                        notification_idempotency_key="key-note", upgrade_intent_hash="e" * 64,
                        notification_intent_hash="f" * 64, task_text="Upgrade order-1 to express, then confirm once.")
    recipe = FaultSpec.model_validate({"seed": 1, "primitives": [{"kind": "F2", "target_tool": "update_order",
        "target_service": "orders", "occurrence": 1,
        "parameters": {"completion_delay_ticks": 5, "terminal_status": "SUCCEEDED", "failure_code": None}}]})
    scenario_hash = content_hash(recipe.model_dump(mode="json"))
    report = TaskReport.model_validate({"upgrade_outcome": "PENDING", "notification_outcome": "SUCCEEDED",
                                        "overall": "COMPLETED", "evidence_ids": ["ev-2"], "next_action": {"kind": "NONE"}})
    verdict = Verdict(verdict_id="verdict-1", episode_id=episode_id, outcome="VIOLATION", checks=_checks(failed=("C3",)),
                      evidence_ids=["ev-1", "ev-2"], supported_completion=False, useful_resolution="invalid",
                      fault_executions=[FaultExecution(fault_id="fault-1", scheduled=True, triggered=True, trigger_tick=1,
                                                       call_id="call-1", attempt_id="att-1")],
                      upgrade_effects=1, notification_effects=1, decision_tick=3, horizon_tick=8, scorer_hash=DIGEST_A)
    episode = Episode(campaign_id="campaign-1", episode_id=episode_id, origin="faultlab_evaluation", split="development",
                      arm="B0", source_mode="offline_fixture", experiment_purpose="completion_study", trial_index=0,
                      study_id="study-1", evidence_context_id="ctx-1", execution_epoch=0, world_id="world-1", task_id="task-1",
                      scenario_hash=scenario_hash, policy_hash="0" * 64, policy_version="policy-v0",
                      model="deepseek-ai/DeepSeek-V3.1", configuration_hash=config_hash, lifecycle=lifecycle,
                      report=report if with_report else None, verdict=verdict if with_verdict else None,
                      usage=Usage(http_attempts=2, actor_calls=3, model_calls=3, input_tokens=1200, output_tokens=80, ticks=3,
                                  wall_seconds=4.5, cost_dollars=0.002),
                      started_at=utc_now(), ended_at=utc_now(), reason=None if lifecycle == "COMPLETED" else "stopped by test")
    store.put_record("configurations", config_hash, config, immutable=True)
    store.put_record("episodes", episode_id, episode.model_dump(mode="json"))
    store.put_record("trials", episode_id, TrialResult(episode_id=episode_id, world_id="world-1", scenario_hash=scenario_hash,
        policy_hash="0" * 64, arm="B0", trial_index=0, lifecycle="COMPLETED" if lifecycle == "COMPLETED" else "INTERRUPTED",
        outcome="VIOLATION" if with_verdict else None, failed_checks=["C3"] if with_verdict else [], fault_scheduled=True,
        fault_triggered=True, usage=episode.usage).model_dump(mode="json"))
    store.put_record("private_episode_inputs", episode_id, {"intent": intent.model_dump(mode="json"),
                                                            "recipe": recipe.model_dump(mode="json"), "fixture_id": "fixture-1"})
    for service, opid, key, attempt in (("orders", "op-up", "key-up", "att-1"), ("notifications", "op-note", "key-note", "att-2")):
        payload = {"operation_id": opid, "order_id": "order-1", "intent_hash": "e" * 64 if service == "orders" else "f" * 64,
                   "idempotency_key": key}
        store.put_record("journals", f"{episode_id}:{opid}", OperationJournal(
            episode_id=episode_id, operation_id=opid, service=service, intent_hash=payload["intent_hash"],
            payload_hash=content_hash(payload), original_request=canonical_json(payload), attempt_ids=[attempt],
            latest_status="PENDING" if service == "orders" else "SUCCEEDED", terminal_receipt_id=None).model_dump(mode="json"))
    calls = [("call-1", "update_order", "att-1", "ev-1", "PENDING"), ("call-2", "send_confirmation", "att-2", "ev-2", "SUCCEEDED")]
    store.append_event(episode_id, tick=0, type="episode_started", payload={"world_id": "world-1"})
    for tick, (call_id, tool, attempt, evidence, status) in enumerate(calls, start=1):
        store.put_record("tool_calls", call_id, ToolCallRecord(call_id=call_id, episode_id=episode_id, tool=tool, caller="actor",
            hook=None, attempt_ids=[attempt], observation_ids=[evidence], usage=Usage()).model_dump(mode="json"))
        observation = PublicObservation(evidence_id=evidence, episode_id=episode_id, call_id=call_id, delivered_tick=tick,
            result=ToolResult(call_id=call_id, tool=tool, transport="ok",
                              operation_id="op-up" if tool == "update_order" else "op-note", order_id="order-1", status=status))
        store.put_record("observations", evidence, observation.model_dump(mode="json"))
        store.append_event(episode_id, tick=tick, role="actor", type="tool_dispatched", payload={"attempt_id": attempt, "tool": tool},
                           call_id=call_id)
        store.append_event(episode_id, tick=tick, role="actor", type="observation_delivered",
                           payload={"observation": observation.model_dump(mode="json")}, call_id=call_id, evidence_id=evidence)
    if with_report:
        store.append_event(episode_id, tick=3, role="actor", type="report_submitted", payload={"report": report.model_dump(mode="json")})
    if with_verdict:
        store.append_event(episode_id, tick=3, role="referee", type="verdict_recorded", payload={"outcome": "VIOLATION"},
                           visibility="PRIVATE_EVALUATOR")
    world_events = [Event(episode_id=episode_id, seq=seq, tick=tick, role="coordinator", type=kind,
                          payload={"operation_id": opid, "attempt_id": attempt}, visibility="PRIVATE_EVALUATOR").model_dump(mode="json")
                    for seq, (tick, kind, opid, attempt) in enumerate([(1, "http_attempt", "op-up", "att-1"),
                                                                        (1, "operation_accepted", "op-up", "att-1"),
                                                                        (2, "upgrade_committed", "op-up", None),
                                                                        (2, "notification_committed", "op-note", "att-2")], start=1)]
    store.put_record("private_snapshots", episode_id, {"decision": None, "horizon": {
        "schema_version": "faultlab/v1", "world_id": "world-1", "tick": 8, "orders": [{"order_id": "order-1", "secret": "world state"}],
        "operations": [], "notifications": [], "events": world_events}})
    store.close()
    return config_hash, scenario_hash


def test_a_complete_legacy_episode_projects_into_a_sealed_envelope(tmp_path):
    path = tmp_path / "lab.sqlite3"
    config_hash, scenario_hash = write_legacy_store(path)
    with LegacyStore(path) as store:
        assert store.episode_ids() == ["episode-1"]
        facts = load_episode_facts(store, "episode-1")
        envelope = project_episode(facts, store_identity=store.identity())
    validate_structure(json.loads(envelope.model_dump_json()))
    assert envelope.plan.pack_id == "orders.upgrade_then_confirm/v1" and envelope.plan.scenario_id == scenario_hash
    assert envelope.plan.fixture_id == "fixture-1" and envelope.plan.agent.model == "deepseek-ai/DeepSeek-V3.1"
    assert envelope.plan.schedule.seed == 1 and [p.family for p in envelope.plan.schedule.placements] == ["F2"]
    assert envelope.plan.caps.model_calls == 8 and envelope.plan.caps.http_attempts == 18 and envelope.plan.caps.ticks == 20
    assert envelope.plan.environment.digest == DIGEST_B and envelope.plan.properties_digest == DIGEST_A
    assert envelope.attempt.attempt_id == "episode-1" and envelope.attempt.lifecycle == "TERMINAL"
    assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == "VIOLATION"
    assert envelope.outcome.evidence_completeness == "complete" and envelope.outcome.identity.configuration_digest == config_hash
    assert envelope.outcome.cost.model_dump() == {"model_calls": 3, "http_attempts": 2, "input_tokens": 1200, "output_tokens": 80,
                                                  "dollars_measured": 0.002, "dollars_reserved": None, "wall_seconds": 4.5, "ticks": 3}
    kinds = [(event.kind, event.plane, event.source) for event in envelope.events]
    assert kinds[:6] == [("trial_started", "orchestrator", "lab"), ("invoked", "agent_visible", "lab"),
                         ("response_delivered", "agent_visible", "lab"), ("invoked", "agent_visible", "lab"),
                         ("response_delivered", "agent_visible", "lab"), ("claim", "agent_visible", "lab")]
    assert kinds[6] == ("terminal", "evaluator", "lab")
    assert kinds[7:] == [("admitted", "evaluator", "kernel"), ("accepted", "evaluator", "kernel"),
                         ("effect_committed", "evaluator", "kernel"), ("effect_committed", "evaluator", "kernel")]
    invoked = envelope.events[1]
    assert invoked.attempt_ref == "att-1" and invoked.operation_id == "op-up" and invoked.clock == "lab_event" and invoked.clock_sequence == 2
    delivered = envelope.events[4]
    assert delivered.attempt_ref == "att-2" and delivered.operation_id == "op-note" and delivered.source_ref == "/events/4"
    assert all(event.causal_parents == [] for event in envelope.events)
    failed = [finding for finding in envelope.outcome.findings if finding.result == "VIOLATION"]
    assert [finding.property_id for finding in failed] == ["C3"] and failed[0].witnesses == [4]
    assert failed[0].family == "premature_confirmation" and len(envelope.outcome.findings) == 8
    assert envelope.outcome.exposure.required_fault_ids == ["fault-1"] and envelope.outcome.exposure.all_required_triggered is True
    assert envelope.outcome.exposure.faults[0].trigger_time == 1 and envelope.outcome.exposure.faults[0].attempt_ref == "att-1"
    assert envelope.report.status == "DELIVERED" and envelope.report.original["overall"] == "COMPLETED"
    assert envelope.source.kind == "legacy_lab_store" and envelope.source.notes == []
    # Raw world state never enters the envelope; only the kernel's event log does.
    assert "secret" not in envelope.model_dump_json() and "world state" not in envelope.model_dump_json()


def test_incomplete_and_failed_episodes_keep_their_truth(tmp_path):
    path = tmp_path / "lab.sqlite3"
    write_legacy_store(path, episode_id="episode-2", lifecycle="LAB_ERROR", with_verdict=False, with_report=False)
    with LegacyStore(path) as store:
        envelope = project_episode(load_episode_facts(store, "episode-2"))
    assert envelope.outcome.execution == "INFRA_ERROR" and envelope.outcome.task is None
    assert envelope.outcome.findings == [] and envelope.outcome.evidence_completeness == "unavailable"
    assert envelope.report.status == "ABSENT" and envelope.attempt.terminal_reason == "stopped by test"
    assert envelope.outcome.exposure.faults[0].triggered is None and envelope.outcome.exposure.all_required_triggered is None
    assert envelope.attempt.lifecycle == "TERMINAL"


def test_contradictory_records_fail_closed(tmp_path):
    path = tmp_path / "lab.sqlite3"
    write_legacy_store(path)
    with LegacyStore(path) as store:
        facts = load_episode_facts(store, "episode-1")
    broken = json.loads(json.dumps(facts))
    broken["configuration"]["scorer_hash"] = "9" * 64
    with pytest.raises(IntegrityError, match="configuration digest"):
        project_episode(broken)
    foreign = json.loads(json.dumps(facts))
    foreign["observations"][0]["episode_id"] = "episode-other"
    with pytest.raises(IntegrityError, match="Cross-episode"):
        project_episode(foreign)
    with pytest.raises(IntegrityError, match="Unknown or missing"):
        project_episode({"format": "other"})
    with pytest.raises(IntegrityError, match="existing regular file"):
        LegacyStore(tmp_path / "absent.sqlite3")


def test_project_store_reports_every_episode_and_writes_envelopes(tmp_path):
    path = tmp_path / "lab.sqlite3"
    write_legacy_store(path, episode_id="episode-1")
    write_legacy_store(path, episode_id="episode-2", lifecycle="INTERRUPTED", with_verdict=False)
    report = project_store(path, write_dir=tmp_path / "out")
    assert report.ok and report.total == 2 and report.projected == 2 and report.failures == []
    assert report.execution == {"COMPLETED": 1, "STOPPED": 1} and report.task == {"VIOLATION": 1, "None": 1}
    assert report.completeness == {"complete": 1, "unavailable": 1}
    written = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert written == ["episode-1.json", "episode-2.json"]
    validate_structure(json.loads((tmp_path / "out" / "episode-1.json").read_text()))
    assert report.as_dict()["mapping_digest"] == legacy.mapping_digest()
    assert legacy.main([str(path), "--limit", "1"]) == 0


@pytest.mark.skipif(not os.environ.get("FAULTLAB_LEGACY_STORE"), reason="set FAULTLAB_LEGACY_STORE to a historical lab.sqlite3")
def test_every_episode_of_a_historical_store_projects():
    report = project_store(Path(os.environ["FAULTLAB_LEGACY_STORE"]))
    assert report.ok, report.failures[:5]
