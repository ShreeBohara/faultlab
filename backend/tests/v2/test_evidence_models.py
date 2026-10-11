"""Sealed trial envelopes: a round trip survives, any tampering fails closed."""
import json
from pathlib import Path

import pytest

from faultlab.core import IntegrityError, content_hash
from faultlab.evidence import (AgentManifest, EnvSpec, EvidenceEvent, ExecutionIdentity, ExposureSummary, FaultExposure,
                               FaultPlacement, FaultSchedule, Finding, Report, ResultVector, SourceDescriptor,
                               TrialAttempt, TrialPlan, plan_hash, schema_digest, seal, validate_structure)
from faultlab.evidence.models import hashed_payload
from faultlab.evidence import schemas


def _plan():
    return TrialPlan(pack_id="orders.upgrade_then_confirm/v1", scenario_id="scenario-1",
                     agent=AgentManifest(adapter_id="reference", model="deepseek-ai/DeepSeek-V3.1"),
                     environment=EnvSpec(kind="simulator", digest="a" * 64),
                     schedule=FaultSchedule(placements=[FaultPlacement(fault_id="fault-1", family="F2", tool="update_order",
                                                                       service="orders", occurrence=1)], seed=7),
                     protocol_version="faultlab/v1")


def _envelope(**overrides):
    plan = _plan()
    facts = {"events": [{"type": "tool_dispatched", "seq": 1}, {"type": "observation_delivered", "seq": 2}],
             "episode": {"report": {"overall": "COMPLETED"}}}
    events = [EvidenceEvent(seq=0, plane="agent_visible", kind="invoked", source="lab", certainty="observed",
                            attempt_ref="att-1", operation_id="op-1", logical_time=1, clock="lab_event", clock_sequence=1,
                            **hashed_payload({"tool": "update_order"}), source_ref="/events/0"),
              EvidenceEvent(seq=1, plane="agent_visible", kind="response_delivered", source="lab", certainty="observed",
                            attempt_ref="att-1", causal_parents=[0], logical_time=2, clock="lab_event", clock_sequence=2,
                            **hashed_payload({"status": "PENDING"}), source_ref="/events/1"),
              EvidenceEvent(seq=2, plane="evaluator", kind="effect_committed", source="kernel", certainty="observed",
                            operation_id="op-1", logical_time=3, clock="world_event", clock_sequence=4,
                            **hashed_payload({"type": "upgrade_committed"}))]
    outcome = ResultVector(execution="COMPLETED", task="VIOLATION",
                           findings=[Finding(property_id="C3", property_version="b" * 64, result="VIOLATION",
                                             family="premature_confirmation", severity="major", witnesses=[1])],
                           exposure=ExposureSummary(faults=[FaultExposure(fault_id="fault-1", triggered=True, trigger_time=3)],
                                                    required_fault_ids=["fault-1"]),
                           evidence_completeness="complete",
                           identity=ExecutionIdentity(pack_id="orders.upgrade_then_confirm/v1", adapter_id="reference",
                                                      model="deepseek-ai/DeepSeek-V3.1", protocol_version="faultlab/v1"))
    fields = dict(plan=plan, attempt=TrialAttempt(attempt_id="episode-1", plan_hash=plan_hash(plan), lifecycle="TERMINAL"),
                  events=events, report=Report(status="DELIVERED", original={"overall": "COMPLETED"}, source_ref="/episode/report"),
                  outcome=outcome, source=SourceDescriptor(kind="faultlab_v2", projection="test", mapping_digest="c" * 64),
                  source_facts=facts)
    fields.update(overrides)
    return seal(**fields)


def test_sealed_envelope_round_trips_through_json_and_keeps_its_digests():
    envelope = _envelope()
    assert envelope.schema_digest == schema_digest() and envelope.facts_digest == content_hash(envelope.source_facts)
    body = envelope.model_dump(mode="json")
    body.pop("digest")
    assert envelope.digest == content_hash(body)
    reloaded = validate_structure(json.loads(envelope.model_dump_json()))
    assert reloaded == envelope
    assert reloaded.outcome.exposure.all_required_triggered is True
    assert [event.kind for event in reloaded.events] == ["invoked", "response_delivered", "effect_committed"]


@pytest.mark.parametrize("tamper", [
    lambda body: body["events"][0]["payload"].update(tool="send_confirmation"),
    lambda body: body["source_facts"]["events"].append({"type": "extra"}),
    lambda body: body["outcome"].update(task="COMPLETED"),
    lambda body: body["attempt"].update(plan_hash="d" * 64),
    lambda body: body.update(schema_digest="e" * 64),
    lambda body: body["plan"]["schedule"].update(seed=8),
])
def test_any_change_after_sealing_is_refused(tamper):
    body = json.loads(_envelope().model_dump_json())
    tamper(body)
    with pytest.raises(IntegrityError):
        validate_structure(body)


def test_structural_contradictions_are_refused_at_sealing():
    with pytest.raises(IntegrityError, match="cites an event"):
        _envelope(outcome=_envelope().outcome.model_copy(update={"findings": [
            Finding(property_id="C3", property_version="v", result="VIOLATION", family="x", severity="major", witnesses=[9])]}))
    with pytest.raises(IntegrityError, match="Required faults"):
        _envelope(outcome=_envelope().outcome.model_copy(update={"exposure": ExposureSummary(required_fault_ids=["ghost"])}))
    with pytest.raises(IntegrityError, match="Absent report"):
        _envelope(report=Report(status="ABSENT", original={"x": 1}))
    with pytest.raises(IntegrityError, match="Delivered report"):
        _envelope(report=Report(status="DELIVERED"))
    with pytest.raises(IntegrityError, match="Dangling source reference"):
        _envelope(report=Report(status="DELIVERED", original={}, source_ref="/episode/missing"))
    with pytest.raises(IntegrityError, match="causal parent"):
        _envelope(events=[EvidenceEvent(seq=0, plane="evaluator", kind="x", source="kernel", certainty="observed",
                                        causal_parents=[0], **hashed_payload({}))])
    with pytest.raises(IntegrityError, match="strictly increasing"):
        _envelope(events=[EvidenceEvent(seq=1, plane="evaluator", kind="x", source="kernel", certainty="observed", **hashed_payload({})),
                          EvidenceEvent(seq=1, plane="evaluator", kind="y", source="kernel", certainty="observed", **hashed_payload({}))])
    with pytest.raises(ValueError, match="task outcome"):
        ResultVector(execution="COMPLETED", task=None, evidence_completeness="complete",
                     identity=ExecutionIdentity(pack_id="p", adapter_id="a", model="m", protocol_version="v"))


def test_exposure_summary_distinguishes_unknown_from_false():
    assert ExposureSummary(required_fault_ids=["f"], faults=[FaultExposure(fault_id="f", triggered=None)]).all_required_triggered is None
    assert ExposureSummary(required_fault_ids=["f"], faults=[FaultExposure(fault_id="f", triggered=False,
                                                                           not_triggered_reason="target_not_reached")]).all_required_triggered is False
    assert ExposureSummary().all_required_triggered is True


def test_committed_schema_documents_are_current(tmp_path):
    committed = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "v2"
    written = schemas.export(tmp_path)
    assert {path.name for path in written} == {"TrialEnvelope.schema.json", "TrialPlan.schema.json", "TrialAttempt.schema.json",
                                               "EvidenceEvent.schema.json", "Finding.schema.json", "ResultVector.schema.json",
                                               "README.md"}
    for path in written:
        assert (committed / path.name).read_text() == path.read_text(), f"stale {path.name}: regenerate docs/schemas/v2"
