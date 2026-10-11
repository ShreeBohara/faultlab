"""The trial worker (plan phase 1.5): one plan, one attempt, one sealed envelope.

The worker is the legacy ``EpisodeRunner`` rebuilt on the v2 pieces: it loads the pack a plan
names and refuses a plan whose pack digest it cannot reproduce, allocates the trial's intent,
creates the world on the kernel through a transport, lends the adapter a ``TrialSession``, runs
it under the plan's caps, then settles the world (stop, decision snapshot, observer horizon),
gathers the three evidence planes and seals a ``TrialEnvelope`` into the store.

Scoring is pluggable and separate. A ``Referee`` turns a sealed draft into a task outcome and
findings; without one the execution stays ``PENDING_EVIDENCE`` (the verdict is missing, exactly
as the legacy projection says of an unscored episode). The belief-versus-effect oracle fills the
claim score for packs that have one. Nothing here weakens or re-implements a fixed check.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from effectsafe import Journal, UnsafeResend
from faultlab.core import Caps, StrictModel, canonical_json, content_hash, new_id, tree_digest, utc_now_text
from faultlab.env.kernel import KernelLimits, WorldError, WorldStore
import faultlab.env.kernel as kernel_package
from faultlab.evidence.legacy import WORLD_EVENT_KINDS
from faultlab.evidence.models import (CostSummary, EvidenceEvent, ExecutionIdentity, ExposureSummary, FaultExposure, Finding,
                                      Report, ResultVector, SourceDescriptor, TaskState, TrialAttempt, TrialEnvelope, TrialPlan,
                                      hashed_payload, plan_hash, seal)
from faultlab.lab.session import CapExhausted, ProtocolError, TrialSession
from faultlab.lab.store import TrialStore
from faultlab.lab.transport import KernelTransport
from faultlab.packs import PackError, TaskPack, load_pack

FACTS_FORMAT = "faultlab-v2-trial-facts/v1"
PROJECTION = "faultlab-v2-trial-worker/v1"
NOT_TRIGGERED = {"target_not_reached", "target_not_committed", "pre_effect_failure", "avoided_by_alternative_path"}
DEFAULT_WALL_SECONDS = 90.0


@runtime_checkable
class Adapter(Protocol):
    """What drives an agent through a session (the seed of the phase 1.6 adapter interface)."""
    adapter_id: str

    async def act(self, session: TrialSession) -> Any: ...


class Verdict(StrictModel):
    task: TaskState | None                     # None: the referee found the execution itself invalid
    findings: list[Finding] = Field(default_factory=list, max_length=256)
    note: str = Field(default="", max_length=600)


class ScoringContext(StrictModel):
    """What a referee may read beyond the sealed draft: the world's private snapshots and the session's facts."""
    intent: dict[str, Any]
    observations: list[dict[str, Any]]
    decision: Any = None                         # the handler's snapshot at the decision tick (private, never in the envelope)
    horizon: Any = None                          # the handler's snapshot after the observer horizon
    fault_executions: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    execution: str
    reason: str | None = None


class Referee(Protocol):
    def score(self, envelope: TrialEnvelope, context: ScoringContext) -> Verdict: ...


class Oracle(Protocol):
    def score(self, envelope: TrialEnvelope): ...


def mapping_digest() -> str:
    from hashlib import sha256
    return sha256(Path(__file__).read_bytes()).hexdigest()


def kernel_digest() -> str:
    return tree_digest(Path(kernel_package.__file__).parent)


def default_oracles() -> dict:
    from faultlab.referee.oracle import orders
    return {orders.PACK_ID: orders.score}


class TrialWorker:
    def __init__(self, *, store: TrialStore, worker_id: str | None = None, database_dir=None, referee: Referee | None = None,
                 oracles: dict | None = None, timeout_seconds: float = 1.0, max_attempts_per_call: int = 2,
                 load=load_pack):
        self.store = store
        self.worker_id = worker_id or new_id("worker")
        if database_dir is None and store.path == ":memory:":
            raise ValueError("An in-memory trial store needs an explicit directory for its worlds")
        self.database_dir = Path(database_dir) if database_dir is not None else Path(store.path).parent / "worlds"
        self.referee = referee
        self.oracles = oracles if oracles is not None else default_oracles()
        self.timeout_seconds = timeout_seconds
        self.max_attempts_per_call = max_attempts_per_call
        self.load = load

    def limits_for(self, plan: TrialPlan) -> KernelLimits:
        defaults = KernelLimits()
        return KernelLimits(http_attempts=plan.caps.http_attempts or defaults.http_attempts, ticks=plan.caps.ticks or defaults.ticks)

    async def run(self, plan: TrialPlan, attempt: TrialAttempt, adapter: Adapter) -> TrialEnvelope:
        """Execute one attempt of a plan and seal its envelope; every exit path leaves a sealed record."""
        digest = plan_hash(plan)
        if attempt.plan_hash != digest:
            raise ProtocolError("The attempt does not name this plan")
        self.store.put_plan(plan)
        attempt = self.store.put_attempt(attempt.model_copy(update={"lifecycle": "RUNNING", "started_at": attempt.started_at or utc_now_text()}),
                                         worker=self.worker_id)
        notes: list[str] = []
        try:
            pack = self.load(plan.pack_id)
            if plan.pack_digest is not None and pack.digest() != plan.pack_digest:
                raise ProtocolError("PACK_DIGEST_MISMATCH")
            if adapter.adapter_id != plan.agent.adapter_id:
                raise ProtocolError("ADAPTER_MISMATCH")
            scenario = pack.scenario(plan.scenario_id)
        except (PackError, ProtocolError) as error:
            return self._seal_unstarted(plan, attempt, str(error), notes)
        return await self._execute(pack, scenario, plan, attempt, adapter, notes)

    async def _execute(self, pack: TaskPack, scenario, plan, attempt, adapter, notes):
        limits = self.limits_for(plan)
        transport = KernelTransport(WorldStore(self.database_dir, pack.handler_factory()), limits, timeout_seconds=self.timeout_seconds)
        intent = pack.allocate_intent(scenario.fixture_id, attempt.attempt_id)
        fault_spec = scenario.fault_spec.model_dump(mode="json")
        try:
            world = transport.create(attempt.attempt_id, intent, fault_spec, scenario.fixture_id)
        except WorldError as error:
            return self._seal_unstarted(plan, attempt, f"WORLD_CREATE_REFUSED:{error.code}", notes)
        journal = Journal(namespace=attempt.attempt_id)
        session = TrialSession(pack=pack, plan=plan, attempt_id=attempt.attempt_id, world_id=world["world_id"], intent=intent,
                               transport=transport, journal=journal, caps=plan.caps, max_attempts_per_call=self.max_attempts_per_call)
        orchestrator: list[dict] = [{"kind": "trial_started", "payload": {"world_id": world["world_id"], "fixture_id": scenario.fixture_id,
                                                                            "adapter_id": adapter.adapter_id}}]
        execution, reason = "COMPLETED", None
        wall = plan.caps.wall_seconds if plan.caps.wall_seconds is not None else DEFAULT_WALL_SECONDS
        started = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(wall):
                returned = await adapter.act(session)
            if returned is not None and not session.report_submitted:
                session.submit(returned)
        except asyncio.CancelledError:
            execution, reason = "STOPPED", "TASK_CANCELLED"
        except TimeoutError:
            reason = "WALL_CAP_REACHED"
        except CapExhausted as error:
            reason = f"CAP_REACHED:{error.cap}"
        except UnsafeResend as error:
            reason = "UNSAFE_RESEND_REFUSED"
            orchestrator.append({"kind": "refused", "payload": {"reason": str(error)[:600]}})
        except ProtocolError as error:
            reason = f"PROTOCOL_ERROR:{str(error)[:200]}"
        except Exception as error:                      # the adapter or its model failed: infrastructure, not the task
            execution, reason = "INFRA_ERROR", f"ADAPTER_ERROR:{type(error).__name__}"
        wall_seconds = asyncio.get_running_loop().time() - started
        session.close()
        attempt = self.store.put_attempt(attempt.model_copy(update={"lifecycle": "SETTLING"}))
        decision = horizon = None
        try:
            decision_tick = transport.stop(world["world_id"])
            decision = transport.snapshot(world["world_id"])
            transport.advance(world["world_id"], limits.horizon_ticks, observer=True)
            horizon = transport.snapshot(world["world_id"])
            state = transport.state(world["world_id"])
            faults = state["fault_executions"]
            world_events = state["events"]
            horizon_tick = state["tick"]
        except WorldError as error:
            execution, reason = "INFRA_ERROR", f"WORLD_SETTLE_FAILED:{error.code}"
            decision_tick, horizon_tick, faults, world_events = session.usage.ticks, session.usage.ticks, [], []
            notes.append("WORLD_UNSETTLED")
        finally:
            journal.close()
        orchestrator.append({"kind": "stopped", "payload": {"decision_tick": decision_tick, "horizon_tick": horizon_tick, "reason": reason}})
        context = ScoringContext(intent=intent, observations=[o.model_dump(mode="json") for o in session.observations],
                                 decision=_json(decision), horizon=_json(horizon), fault_executions=faults,
                                 usage=session.usage.model_dump(mode="json"), execution=execution, reason=reason)
        return self._seal(pack, plan, attempt, adapter, session, intent, world, fault_spec, scenario, execution, reason, wall_seconds,
                          decision_tick, faults, world_events, orchestrator, notes, context)

    def _seal_unstarted(self, plan, attempt, reason, notes):
        attempt = attempt.model_copy(update={"lifecycle": "TERMINAL", "terminal_reason": reason[:600], "ended_at": utc_now_text()})
        facts = {"format": FACTS_FORMAT, "plan": plan.model_dump(mode="json"), "attempt": attempt.model_dump(mode="json"),
                 "intent": None, "world": None, "calls": [], "events": [], "world_events": [], "fault_executions": [],
                 "report": None, "usage": None}
        event = EvidenceEvent(seq=0, plane="orchestrator", kind="refused", source="lab", certainty="observed",
                              **hashed_payload({"reason": reason}), wall_time=utc_now_text(), clock="session", clock_sequence=0)
        identity = ExecutionIdentity(pack_id=plan.pack_id, pack_digest=plan.pack_digest, adapter_id=plan.agent.adapter_id,
                                     model=plan.agent.model, model_settings_digest=plan.agent.settings_digest,
                                     prompt_digest=plan.agent.prompt_digest, properties_digest=plan.properties_digest,
                                     protocol_version=plan.protocol_version)
        outcome = ResultVector(execution="INFRA_ERROR", task=None, evidence_completeness="unavailable",
                               exposure=ExposureSummary(faults=[FaultExposure(fault_id=p.fault_id, configured=True, triggered=None)
                                                                for p in plan.schedule.placements],
                                                        required_fault_ids=[p.fault_id for p in plan.schedule.placements]),
                               cost=CostSummary(dollars_reserved=plan.caps.dollars), identity=identity)
        envelope = seal(plan=plan, attempt=attempt, events=[event], report=Report(status="ABSENT"), outcome=outcome,
                        source=SourceDescriptor(kind="faultlab_v2", projection=PROJECTION, mapping_digest=mapping_digest(),
                                                store_identity=Path(self.store.path).name, notes=[*notes, reason[:2000]]),
                        source_facts=facts)
        return self.store.put_envelope(envelope)

    def _seal(self, pack, plan, attempt, adapter, session: TrialSession, intent, world, fault_spec, scenario, execution, reason,
              wall_seconds, decision_tick, faults, world_events, orchestrator, notes, context: ScoringContext):
        usage = session.usage
        events: list[EvidenceEvent] = []
        for item in orchestrator[:1]:
            events.append(self._lab_event(len(events), "orchestrator", item["kind"], item["payload"], "/orchestrator/0", usage.ticks))
        agent_events = session.events
        for index, event in enumerate(agent_events):
            events.append(event.model_copy(update={"seq": len(events), "source_ref": f"/events/{index}"}))
        for index, item in enumerate(orchestrator[1:], start=1):
            events.append(self._lab_event(len(events), "orchestrator", item["kind"], item["payload"], f"/orchestrator/{index}", usage.ticks))
        for index, event in enumerate(world_events):
            payload = event.get("payload", {})
            events.append(EvidenceEvent(
                seq=len(events), plane="evaluator", kind=WORLD_EVENT_KINDS.get(event["type"], event["type"]), source="kernel",
                certainty="observed", operation_id=payload.get("operation_id") if isinstance(payload.get("operation_id"), str) else None,
                attempt_ref=payload.get("attempt_id") if isinstance(payload.get("attempt_id"), str) else None,
                logical_time=event.get("tick"), wall_time=event.get("at"), clock="world_event", clock_sequence=event.get("seq"),
                **hashed_payload(event), source_ref=f"/world_events/{index}"))
        placements = plan.schedule.placements
        exposure_faults = []
        for index, record in enumerate(faults):
            placement_id = placements[index].fault_id if index < len(placements) else str(record["fault_id"])
            triggered = record.get("triggered")
            why = record.get("reason")
            exposure_faults.append(FaultExposure(
                fault_id=placement_id, configured=bool(record.get("scheduled", True)), triggered=triggered if isinstance(triggered, bool) else None,
                trigger_time=record.get("trigger_tick") if isinstance(record.get("trigger_tick"), int) else None,
                attempt_ref=record.get("attempt_id") if isinstance(record.get("attempt_id"), str) else None,
                not_triggered_reason=None if triggered else (why if why in NOT_TRIGGERED else "unclassified"),
                note=f"kernel fault {record['fault_id']}"))
        if len(faults) != len(placements):
            notes.append("EXPOSURE_PLACEMENT_COUNT_MISMATCH")
        exposure = ExposureSummary(faults=exposure_faults, required_fault_ids=[f.fault_id for f in exposure_faults if f.configured])
        report = (Report(status="DELIVERED", original=session.report, source_ref="/report",
                         interpreted=_interpreted(pack, session.report)) if session.report_submitted
                  else Report(status="ABSENT", source_ref="/report"))
        cost = CostSummary(model_calls=usage.model_calls, http_attempts=usage.http_attempts, input_tokens=usage.input_tokens,
                           output_tokens=usage.output_tokens, dollars_measured=usage.dollars_measured, dollars_reserved=plan.caps.dollars,
                           wall_seconds=max(0.0, wall_seconds), ticks=decision_tick)
        configuration = {"plan_hash": plan_hash(plan), "transport": session.transport.descriptor, "max_attempts_per_call": self.max_attempts_per_call,
                         "worker_mapping_digest": mapping_digest()}
        adapter_digest = getattr(adapter, "digest", None)
        identity = ExecutionIdentity(
            pack_id=plan.pack_id, pack_digest=pack.digest(), kernel_digest=kernel_digest(), adapter_id=plan.agent.adapter_id,
            adapter_digest=adapter_digest if isinstance(adapter_digest, str) else None, model=plan.agent.model,
            model_settings_digest=plan.agent.settings_digest, prompt_digest=plan.agent.prompt_digest,
            properties_digest=plan.properties_digest, protocol_version=plan.protocol_version, configuration_digest=content_hash(configuration))
        attempt = attempt.model_copy(update={"lifecycle": "TERMINAL", "terminal_reason": reason, "ended_at": utc_now_text()})
        facts = {"format": FACTS_FORMAT, "plan": plan.model_dump(mode="json"), "attempt": attempt.model_dump(mode="json"),
                 "intent": intent, "world": {"world_id": world["world_id"], "fixture_id": scenario.fixture_id, "fault_spec": fault_spec,
                                             "configuration": configuration},
                 "calls": session.calls, "events": [e.model_dump(mode="json") for e in agent_events],
                 "orchestrator": orchestrator, "world_events": world_events, "fault_executions": faults,
                 "report": session.report if session.report_submitted else None, "usage": usage.model_dump(mode="json")}
        # First seal: the execution evidence with the task outcome still pending (a valid envelope in its own
        # right). The oracle and the referee read that sealed draft; the final seal carries their results.
        completeness = "complete" if execution != "INFRA_ERROR" and "WORLD_UNSETTLED" not in notes else "incomplete"
        scored = execution == "COMPLETED" and self.referee is not None
        if execution == "COMPLETED" and not scored:
            notes.append("TASK_OUTCOME_UNSCORED")
        draft_execution = "PENDING_EVIDENCE" if execution == "COMPLETED" else execution
        outcome = ResultVector(execution=draft_execution, task=None, findings=[], exposure=exposure, evidence_completeness=completeness,
                               cost=cost, identity=identity)
        source = SourceDescriptor(kind="faultlab_v2", projection=PROJECTION, mapping_digest=mapping_digest(),
                                  store_identity=Path(self.store.path).name, notes=list(notes))
        draft = seal(plan=plan, attempt=attempt, events=events, report=report, outcome=outcome, source=source, source_facts=facts)
        outcome_value, source_notes = outcome.model_dump(mode="json"), list(source.notes)
        oracle = self.oracles.get(plan.pack_id)
        if oracle is not None:
            try:
                outcome_value["claims"] = oracle(draft).to_claim_score()
            except Exception as error:                   # an oracle failure is noted, never hidden behind UNSCORED silently
                source_notes.append(f"ORACLE_FAILED:{type(error).__name__}"[:2000])
        if scored:
            try:
                verdict = self.referee.score(draft, context)
            except Exception as error:                   # a referee that fails leaves the outcome pending, never guessed
                verdict = None
                source_notes.append(f"REFEREE_FAILED:{type(error).__name__}:{str(error)[:160]}"[:2000])
            if verdict is not None and verdict.task is not None:
                outcome_value["execution"] = "COMPLETED"
                outcome_value["task"] = verdict.task
                outcome_value["findings"] = [finding.model_dump(mode="json") for finding in verdict.findings]
            elif verdict is not None:
                outcome_value["execution"] = "INFRA_ERROR"
                outcome_value["evidence_completeness"] = "incomplete"
                outcome_value["findings"] = [finding.model_dump(mode="json") for finding in verdict.findings]
                source_notes.append("REFEREE_FOUND_EXECUTION_INVALID")
            if verdict is not None and verdict.note:
                source_notes.append(verdict.note)
        outcome = ResultVector.model_validate(outcome_value)
        source = SourceDescriptor.model_validate({**source.model_dump(mode="json"), "notes": source_notes})
        envelope = seal(plan=plan, attempt=attempt, events=events, report=report, outcome=outcome, source=source, source_facts=facts)
        return self.store.put_envelope(envelope)

    @staticmethod
    def _lab_event(seq, plane, kind, payload, source_ref, tick):
        return EvidenceEvent(seq=seq, plane=plane, kind=kind, source="lab", certainty="observed", logical_time=tick,
                             wall_time=utc_now_text(), clock="session", clock_sequence=seq, **hashed_payload(payload), source_ref=source_ref)


def _interpreted(pack, report):
    try:
        return pack.report_model.model_validate(report).model_dump(mode="json")
    except (TypeError, ValueError):
        return None


def _json(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


__all__ = ["Adapter", "FACTS_FORMAT", "PROJECTION", "Referee", "ScoringContext", "TrialWorker", "Verdict", "kernel_digest",
           "mapping_digest"]
