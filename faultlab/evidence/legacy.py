"""Project a legacy lab episode (FaultLab v1, ``backend/app``) into a v2 trial envelope.

This is the first migration tool of the strangler refactor: every historical store stays
readable, and each saved episode can be presented as a sealed ``TrialEnvelope`` without
touching the store. The reader opens SQLite read-only and never imports the legacy ``app``
package; the record shapes it relies on are the v1 wire contracts (``app/contracts/models.py``),
checked structurally here. Contradictions fail closed as ``IntegrityError`` so a projection
run reports exactly which episodes could not be represented and why.

Nothing is re-scored. Findings are the persisted C1-C8 results; exposure is the persisted
fault ledger; the outcome vector only re-labels the legacy outcome vocabulary.

Run ``python -m faultlab.evidence.legacy <store.sqlite3>`` to project a whole store.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

from faultlab.core.canonical import canonical_json, content_hash
from faultlab.core.errors import IntegrityError
from faultlab.core.ids import is_digest, is_id
from faultlab.evidence.models import (MAX_BYTES, AgentManifest, Caps, CostSummary, EnvSpec, EvidenceEvent,
                                      ExecutionIdentity, ExposureSummary, FaultExposure, FaultPlacement,
                                      FaultSchedule, Finding, RepetitionPolicy, Report, ResultVector,
                                      SourceDescriptor, TrialAttempt, TrialEnvelope, TrialPlan, hashed_payload,
                                      plan_hash, seal)

PROJECTION = "faultlab-legacy-episode-projection/v1"
FACTS_FORMAT = "faultlab-legacy-episode-facts/v1"
LEGACY_PACK = "orders.upgrade_then_confirm/v1"
LEGACY_PROTOCOL = "faultlab/v1"
FACT_KEYS = frozenset({"format", "episode", "trial", "configuration", "inputs", "journals", "tool_calls",
                       "observations", "events", "world_events", "executions"})

# Lab event type -> (v2 kind, plane). Unknown types keep their name and take the plane of their visibility.
LAB_EVENT_KINDS = {
    "episode_started": ("trial_started", "orchestrator"),
    "tool_dispatched": ("invoked", "agent_visible"),
    "observation_delivered": ("response_delivered", "agent_visible"),
    "wait_completed": ("waited", "agent_visible"),
    "policy_step": ("rule_step", "agent_visible"),
    "actor_transport_retry": ("model_transport_retry", "orchestrator"),
    "report_submitted": ("claim", "agent_visible"),
    "verdict_recorded": ("terminal", "evaluator"),
    "episode_interrupted": ("stopped", "orchestrator"),
}
PLANE_BY_VISIBILITY = {"PUBLIC_OBSERVATION": "agent_visible", "DEVELOPMENT_DIAGNOSTIC": "orchestrator",
                       "PRIVATE_EVALUATOR": "evaluator"}
# World (kernel) event type -> v2 kind. Only these are read out of the private snapshot; never raw state.
WORLD_EVENT_KINDS = {
    "http_attempt": "admitted", "operation_accepted": "accepted", "upgrade_committed": "effect_committed",
    "notification_committed": "effect_committed", "upgrade_failed": "effect_failed",
    "request_rejected": "rejected", "fault_triggered": "fault_triggered", "world_stopped": "world_stopped",
}
CHECK_FAMILIES = {
    "C1": ("unauthorized_or_duplicate_effect", "critical"), "C2": ("false_success_claim", "critical"),
    "C3": ("premature_confirmation", "major"), "C4": ("confirmation_count", "major"),
    "C5": ("false_report", "critical"), "C6": ("fabricated_citation", "major"),
    "C7": ("false_failure_claim", "major"), "C8": ("disallowed_action", "major"),
}
EXECUTION_BY_LIFECYCLE = {"COMPLETED": "COMPLETED", "INTERRUPTED": "STOPPED", "LAB_ERROR": "INFRA_ERROR"}
TASK_BY_OUTCOME = {"COMPLETED": "COMPLETED", "SAFE_UNRESOLVED": "SAFE_UNRESOLVED",
                   "CORRECTLY_REJECTED": "CORRECTLY_REFUSED", "VIOLATION": "VIOLATION"}


def mapping_digest() -> str:
    return sha256(Path(__file__).read_bytes()).hexdigest()


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


class LegacyStore:
    """Read-only access to a v1 lab store (its ``records`` and ``events`` tables)."""

    def __init__(self, path):
        path = Path(path).expanduser()
        _require(path.is_file() and not path.is_symlink(), "Legacy store must be an existing regular file")
        self.path = path
        try:
            self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            self.db.execute("SELECT 1 FROM records LIMIT 1")
        except sqlite3.Error:
            # A WAL store without its side files refuses a strictly read-only open; fall back to a
            # connection that may create them but can never write records.
            self.db = sqlite3.connect(str(path))
            self.db.execute("PRAGMA query_only=ON")
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def record(self, kind, id):
        if not isinstance(id, str):
            return None
        row = self.db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        return None if row is None else json.loads(row["payload"])

    def rows(self, kind, episode_id):
        raw = self.db.execute(
            "SELECT payload FROM records WHERE kind=? AND json_extract(payload,'$.episode_id')=? ORDER BY rowid",
            (kind, episode_id)).fetchall()
        return [json.loads(row["payload"]) for row in raw]

    def events(self, episode_id):
        raw = self.db.execute("SELECT payload FROM events WHERE episode_id=? ORDER BY seq", (episode_id,)).fetchall()
        return [json.loads(row["payload"]) for row in raw]

    def episode_ids(self):
        rows = self.db.execute("SELECT id FROM records WHERE kind='episodes' ORDER BY rowid").fetchall()
        return [row["id"] for row in rows]

    def identity(self) -> str:
        count = self.db.execute("SELECT COUNT(*) FROM records WHERE kind='episodes'").fetchone()[0]
        return content_hash({"kind": "legacy_lab_store", "file": self.path.name, "episodes": count})


def load_episode_facts(store: LegacyStore, episode_id: str) -> dict:
    """The closed set of records one legacy episode is projected from."""
    episode = store.record("episodes", episode_id)
    _require(isinstance(episode, dict) and episode.get("episode_id") == episode_id, "Legacy episode is unavailable")
    snapshots = store.record("private_snapshots", episode_id)
    world_events = []
    if isinstance(snapshots, dict):
        snapshot = snapshots.get("horizon") or snapshots.get("decision")
        if isinstance(snapshot, dict):
            # The snapshot's event log establishes dispatch, effects and exposure; its orders,
            # operations and notifications (raw world state) are deliberately not read out.
            world_events = [event for event in snapshot.get("events", [])
                            if isinstance(event, dict) and event.get("type") in WORLD_EVENT_KINDS]
    return {
        "format": FACTS_FORMAT,
        "episode": episode,
        "trial": store.record("trials", episode_id),
        "configuration": store.record("configurations", episode.get("configuration_hash")),
        "inputs": store.record("private_episode_inputs", episode_id),
        "journals": store.rows("journals", episode_id),
        "tool_calls": store.rows("tool_calls", episode_id),
        "observations": store.rows("observations", episode_id),
        "events": store.events(episode_id),
        "world_events": world_events,
        "executions": {"native": store.record("native_agent_executions", episode_id),
                       "registered": store.record("episode_executions", episode_id),
                       "offline": store.record("offline_fixture_executions", episode_id)},
    }


def _digest_or_none(value):
    return value if is_digest(value) else None


def _id_or_none(value):
    return value if is_id(value) else None


def _placements(recipe):
    placements = []
    if not isinstance(recipe, dict):
        return placements, None
    for index, primitive in enumerate(recipe.get("primitives", []) or []):
        if not isinstance(primitive, dict):
            continue
        kind = primitive.get("kind")
        tool, service, occurrence = primitive.get("target_tool"), primitive.get("target_service"), primitive.get("occurrence")
        fault_id = primitive.get("fault_id") or primitive.get("id") or f"{kind}:{service}:{tool}:{occurrence}:{index}"
        parameters = primitive.get("parameters") if isinstance(primitive.get("parameters"), dict) else {}
        placements.append(FaultPlacement(fault_id=str(fault_id), family=str(kind), tool=tool if isinstance(tool, str) else None,
                                         service=service if isinstance(service, str) else None,
                                         occurrence=occurrence if isinstance(occurrence, int) and occurrence >= 1 else None,
                                         parameters=parameters))
    seed = recipe.get("seed")
    return placements, seed if isinstance(seed, int) else None


def project_episode(facts: dict, *, store_identity: str | None = None) -> TrialEnvelope:
    """Project closed source facts into a sealed envelope; contradictions fail closed."""
    _require(isinstance(facts, dict) and set(facts) == FACT_KEYS and facts["format"] == FACTS_FORMAT,
             "Unknown or missing legacy source fields")
    serialized = canonical_json(facts)
    _require(len(serialized.encode("utf-8")) <= MAX_BYTES, "Legacy source facts exceed the envelope bound")
    facts = json.loads(serialized)   # a private copy: callers cannot mutate the sealed facts afterwards
    try:
        return _project(facts, store_identity)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise IntegrityError(f"Invalid or contradictory legacy source facts: {error}") from error


def _project(facts, store_identity):
    notes = []
    episode = facts["episode"]
    _require(isinstance(episode, dict) and is_id(episode.get("episode_id")), "Legacy episode record is malformed")
    eid = episode["episode_id"]
    config = facts["configuration"]
    if isinstance(config, dict):
        _require(content_hash(config) == episode.get("configuration_hash"), "Legacy configuration digest mismatch")
    else:
        config = {}
        notes.append("CONFIGURATION_UNAVAILABLE")
    inputs = facts["inputs"] if isinstance(facts["inputs"], dict) else {}
    if not inputs:
        notes.append("DECLARED_INPUTS_UNAVAILABLE")
    trial = facts["trial"]
    if trial is None:
        notes.append("TRIAL_UNAVAILABLE")
    verdict = episode.get("verdict")
    if verdict is not None:
        _require(isinstance(verdict, dict) and verdict.get("episode_id") == eid, "Legacy verdict belongs to another episode")
    for row in [*facts["journals"], *facts["tool_calls"], *facts["observations"], *facts["events"]]:
        _require(isinstance(row, dict) and row.get("episode_id") == eid, "Cross-episode legacy evidence")

    # Joins: attempt -> operation (write journals) and observation -> attempt (tool call records).
    attempt_operation = {}
    for journal in facts["journals"]:
        for attempt_id in journal.get("attempt_ids", []):
            _require(attempt_id not in attempt_operation, "Duplicate legacy journal attempt")
            attempt_operation[attempt_id] = journal.get("operation_id")
    observation_attempt = {}
    for call in facts["tool_calls"]:
        attempt_ids, observation_ids = call.get("attempt_ids", []), call.get("observation_ids", [])
        _require(len(observation_ids) <= len(attempt_ids), "More observations than attempts in a legacy call")
        for index, observation_id in enumerate(observation_ids):
            _require(observation_id not in observation_attempt, "Observation appears in more than one legacy call")
            observation_attempt[observation_id] = attempt_ids[index]

    events = []
    witness_seq_by_evidence = {}
    lab_events = facts["events"]
    _require([event.get("seq") for event in lab_events] == sorted(event.get("seq") for event in lab_events),
             "Unordered legacy event sequence")
    for index, event in enumerate(lab_events):
        legacy_type = event.get("type")
        kind, plane = LAB_EVENT_KINDS.get(legacy_type, (None, None))
        if kind is None:
            kind = legacy_type if isinstance(legacy_type, str) else "unknown"
            plane = PLANE_BY_VISIBILITY.get(event.get("visibility"), "orchestrator")
        payload = event.get("payload", {})
        attempt_ref = None
        if legacy_type == "tool_dispatched":
            attempt_ref = _id_or_none(payload.get("attempt_id"))
        elif legacy_type == "observation_delivered":
            attempt_ref = _id_or_none(observation_attempt.get(event.get("evidence_id")))
        operation_id = _id_or_none(attempt_operation.get(attempt_ref)) if attempt_ref else None
        seq = len(events)
        events.append(EvidenceEvent(
            seq=seq, plane=plane, kind=kind, source="lab", certainty="observed",
            operation_id=operation_id, attempt_ref=attempt_ref,
            logical_time=event.get("tick") if isinstance(event.get("tick"), int) else None,
            wall_time=event.get("at") if isinstance(event.get("at"), str) else None,
            clock="lab_event", clock_sequence=event.get("seq") if isinstance(event.get("seq"), int) else None,
            **hashed_payload(payload), source_ref=f"/events/{index}"))
        if legacy_type == "observation_delivered" and isinstance(event.get("evidence_id"), str):
            witness_seq_by_evidence[event["evidence_id"]] = seq
    for index, event in enumerate(facts["world_events"]):
        payload = event.get("payload", {})
        seq = len(events)
        events.append(EvidenceEvent(
            seq=seq, plane="evaluator", kind=WORLD_EVENT_KINDS[event["type"]], source="kernel", certainty="observed",
            operation_id=_id_or_none(payload.get("operation_id") if isinstance(payload, dict) else None),
            attempt_ref=_id_or_none(payload.get("attempt_id") if isinstance(payload, dict) else None),
            logical_time=event.get("tick") if isinstance(event.get("tick"), int) else None,
            wall_time=event.get("at") if isinstance(event.get("at"), str) else None,
            clock="world_event", clock_sequence=event.get("seq") if isinstance(event.get("seq"), int) else None,
            **hashed_payload(event), source_ref=f"/world_events/{index}"))

    placements, seed = _placements(inputs.get("recipe"))
    budget = config.get("episode_budget") if isinstance(config.get("episode_budget"), dict) else {}
    caps = Caps(model_calls=budget.get("actor_calls"), http_attempts=budget.get("http_attempts"),
                ticks=budget.get("ticks"), wall_seconds=budget.get("wall_seconds"))
    scorer_digest = _digest_or_none((verdict or {}).get("scorer_hash")) or _digest_or_none(config.get("scorer_hash"))
    model_settings = config.get("model_settings")
    plan = TrialPlan(
        pack_id=LEGACY_PACK, scenario_id=str(episode.get("scenario_hash")),
        fixture_id=inputs.get("fixture_id") if isinstance(inputs.get("fixture_id"), str) else None,
        agent=AgentManifest(adapter_id=str(episode.get("agent_registration_id") or "orders-v1"), model=str(episode.get("model")),
                            settings_digest=content_hash(model_settings) if isinstance(model_settings, dict) else None,
                            prompt_digest=_digest_or_none(config.get("actor_prompt_hash"))),
        environment=EnvSpec(kind="simulator", digest=_digest_or_none(config.get("service_hash"))),
        schedule=FaultSchedule(placements=placements, seed=seed),
        properties_digest=scorer_digest, protocol_version=LEGACY_PROTOCOL, caps=caps,
        repetition=RepetitionPolicy(k=1, pairing=str(episode.get("arm")) if episode.get("arm") else None))
    lifecycle = episode.get("lifecycle")
    attempt = TrialAttempt(
        attempt_id=eid, plan_hash=plan_hash(plan),
        lifecycle="TERMINAL" if lifecycle in EXECUTION_BY_LIFECYCLE else "RUNNING" if lifecycle in ("RUNNING", "SCORING") else "CREATED",
        terminal_reason=episode.get("reason") if isinstance(episode.get("reason"), str) else None,
        started_at=episode.get("started_at") if isinstance(episode.get("started_at"), str) else None,
        ended_at=episode.get("ended_at") if isinstance(episode.get("ended_at"), str) else None)

    findings = []
    if verdict is not None:
        for check in verdict.get("checks", []):
            family, severity = CHECK_FAMILIES.get(check.get("check_id"), ("unknown_property", "major"))
            witnesses = sorted({witness_seq_by_evidence[evidence_id] for evidence_id in check.get("evidence_ids", [])
                                if evidence_id in witness_seq_by_evidence})
            findings.append(Finding(property_id=str(check.get("check_id")), property_version=scorer_digest or "unknown",
                                    result="PASS" if check.get("passed") else "VIOLATION", family=family,
                                    severity=severity, witnesses=witnesses,
                                    note=str(check.get("category") or "")[:2000]))
    faults = []
    if verdict is not None and verdict.get("fault_executions"):
        for execution in verdict["fault_executions"]:
            triggered = execution.get("triggered")
            faults.append(FaultExposure(
                fault_id=str(execution.get("fault_id")), configured=bool(execution.get("scheduled", True)),
                triggered=triggered if isinstance(triggered, bool) else None,
                trigger_time=execution.get("trigger_tick") if isinstance(execution.get("trigger_tick"), int) else None,
                attempt_ref=_id_or_none(execution.get("attempt_id")),
                not_triggered_reason="unclassified" if triggered is False else None,
                note=str(execution["reason"])[:600] if execution.get("reason") else None))
    else:
        faults = [FaultExposure(fault_id=placement.fault_id, configured=True, triggered=None) for placement in placements]
    exposure = ExposureSummary(faults=faults, required_fault_ids=[fault.fault_id for fault in faults if fault.configured])

    usage = episode.get("usage") if isinstance(episode.get("usage"), dict) else {}
    cost = CostSummary(model_calls=int(usage.get("model_calls", 0) or 0), http_attempts=int(usage.get("http_attempts", 0) or 0),
                       input_tokens=int(usage.get("input_tokens", 0) or 0), output_tokens=int(usage.get("output_tokens", 0) or 0),
                       dollars_measured=usage.get("cost_dollars") if isinstance(usage.get("cost_dollars"), (int, float)) else None,
                       wall_seconds=float(usage.get("wall_seconds", 0) or 0), ticks=int(usage.get("ticks", 0) or 0))
    identity = ExecutionIdentity(
        pack_id=LEGACY_PACK, kernel_digest=_digest_or_none(config.get("service_hash")),
        adapter_id=plan.agent.adapter_id, adapter_digest=_digest_or_none(config.get("adapter_hash")),
        model=plan.agent.model, model_settings_digest=plan.agent.settings_digest, prompt_digest=plan.agent.prompt_digest,
        properties_digest=scorer_digest, protocol_version=LEGACY_PROTOCOL,
        configuration_digest=_digest_or_none(episode.get("configuration_hash")))
    execution = EXECUTION_BY_LIFECYCLE.get(lifecycle, "PENDING_EVIDENCE")
    outcome_name = (verdict or {}).get("outcome")
    task = TASK_BY_OUTCOME.get(outcome_name)
    if execution == "COMPLETED" and task is None:
        # A completed episode whose verdict is missing or LAB_ERROR has no task outcome: its evidence is pending.
        execution = "PENDING_EVIDENCE" if verdict is None else "INFRA_ERROR"
    if verdict is None:
        completeness = "unavailable"
    elif lifecycle == "COMPLETED" and trial is not None and not notes:
        completeness = "complete"
    else:
        completeness = "incomplete"
    outcome = ResultVector(execution=execution, task=task, findings=findings, exposure=exposure,
                           evidence_completeness=completeness, cost=cost, identity=identity)
    report_value = episode.get("report")
    report = (Report(status="DELIVERED", original=report_value, source_ref="/episode/report") if report_value is not None
              else Report(status="ABSENT", source_ref="/episode/report"))
    source = SourceDescriptor(kind="legacy_lab_store", projection=PROJECTION, mapping_digest=mapping_digest(),
                              store_identity=store_identity, notes=notes)
    return seal(plan=plan, attempt=attempt, events=events, report=report, outcome=outcome, source=source, source_facts=facts)


@dataclass
class ProjectionReport:
    store: str
    store_identity: str
    total: int = 0
    projected: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    execution: dict[str, int] = field(default_factory=dict)
    task: dict[str, int] = field(default_factory=dict)
    completeness: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.projected == self.total

    def as_dict(self) -> dict:
        return {"projection": PROJECTION, "mapping_digest": mapping_digest(), "store": self.store,
                "store_identity": self.store_identity, "total": self.total, "projected": self.projected,
                "ok": self.ok, "failures": self.failures, "execution": self.execution, "task": self.task,
                "completeness": self.completeness}


def project_store(path, *, limit: int | None = None, write_dir=None) -> ProjectionReport:
    """Project every episode of a legacy store; optionally write each envelope as JSON."""
    with LegacyStore(path) as store:
        report = ProjectionReport(store=str(Path(path).expanduser()), store_identity=store.identity())
        ids = store.episode_ids()
        if limit is not None:
            ids = ids[:limit]
        output = Path(write_dir) if write_dir else None
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
        for episode_id in ids:
            report.total += 1
            try:
                envelope = project_episode(load_episode_facts(store, episode_id), store_identity=report.store_identity)
            except IntegrityError as error:
                report.failures.append({"episode_id": episode_id, "reason": str(error)[:500]})
                continue
            report.projected += 1
            for bucket, key in ((report.execution, envelope.outcome.execution), (report.task, envelope.outcome.task),
                                (report.completeness, envelope.outcome.evidence_completeness)):
                bucket[str(key)] = bucket.get(str(key), 0) + 1
            if output is not None:
                (output / f"{episode_id}.json").write_text(canonical_json(envelope) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Project every episode of a legacy FaultLab store into v2 trial envelopes")
    parser.add_argument("store", help="path to a legacy lab.sqlite3 (opened read-only)")
    parser.add_argument("--limit", type=int, default=None, help="project only the first N episodes")
    parser.add_argument("--write", default=None, metavar="DIR", help="write one <episode_id>.json envelope per episode")
    args = parser.parse_args(argv)
    report = project_store(args.store, limit=args.limit, write_dir=args.write)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
