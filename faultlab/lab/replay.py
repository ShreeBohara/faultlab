"""Replay (plan phase 1.8, second part): a sealed envelope's recorded inputs re-issued in a fresh world.

A replay is the reader's own reviewed runner, never code the envelope brought along. The
``ReplayAdapter`` reads the agent-visible record of one envelope (the logical calls with their
requests, the waits, the final report) and re-issues the same steps in order through a new
session, with every identity of the recorded intent rebound to the fresh trial's intent and every
recorded evidence id rebound to the evidence the new world delivers.

Two modes:

* **recorded-input execution with divergence stop**: after each call, what the new world delivered
  is compared with what was recorded (tool, transport, HTTP status, state word, error code). The
  first difference stops the replay and is recorded as a rule step on the new envelope, so a replay
  never pretends the recorded agent would have continued the same way in a different world.
* **cut-point replay**: the first ``cut_at`` logical steps are replayed, then a continuation adapter
  takes over the session (what would a different agent have done from here?).
"""

from __future__ import annotations

from typing import Any, Callable

from faultlab.evidence.models import TrialEnvelope
from faultlab.lab.session import TrialSession

COMPARED = ("tool", "transport", "http_status")
COMPARED_IN_RESULT = ("status", "error_code")


def rebind(value: Any, mapping: dict[str, str]) -> Any:
    """Replace every string equal to a recorded identity with the fresh trial's; structure untouched."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [rebind(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: rebind(item, mapping) for key, item in value.items()}
    return value


def intent_mapping(recorded: dict, fresh: dict) -> dict[str, str]:
    """Old intent field value -> new intent field value, for every string-valued field they share."""
    mapping = {}
    for key, old in recorded.items():
        new = fresh.get(key)
        if isinstance(old, str) and isinstance(new, str) and old != new:
            mapping[old] = new
    return mapping


def recorded_steps(envelope: TrialEnvelope) -> list[dict]:
    """The logical steps of an envelope's agent-visible record, in order: calls, waits, the claim."""
    facts = envelope.source_facts
    calls = {call["call_id"]: call for call in facts.get("calls", []) if isinstance(call, dict)}
    observations = {}
    for event in envelope.events:
        if event.plane == "agent_visible" and event.kind == "response_delivered" and isinstance(event.payload, dict):
            observation = event.payload.get("observation")
            if isinstance(observation, dict):
                observations.setdefault(observation.get("call_id"), []).append(observation)
    steps, seen = [], set()
    for event in envelope.events:
        if event.plane != "agent_visible" or not isinstance(event.payload, dict):
            continue
        if event.kind == "invoked":
            call_id = event.payload.get("call_id")
            if call_id in seen or call_id not in calls:
                continue
            seen.add(call_id)
            steps.append({"kind": "call", "call": calls[call_id], "observations": observations.get(call_id, [])})
        elif event.kind == "waited":
            steps.append({"kind": "wait", "ticks": int(event.payload.get("ticks", 1))})
        elif event.kind == "claim":
            steps.append({"kind": "claim", "report": event.payload.get("report")})
    return steps


def shape(observation: dict) -> dict:
    result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
    return {**{key: observation.get(key) for key in COMPARED}, **{key: result.get(key) for key in COMPARED_IN_RESULT}}


class ReplayAdapter:
    """Re-issues one envelope's recorded steps; stops at the first divergence or hands over at the cut point."""

    def __init__(self, envelope: TrialEnvelope, *, cut_at: int | None = None,
                 continuation: Callable[[TrialSession], Any] | None = None, stop_on_divergence: bool = True):
        self.envelope = envelope
        self.adapter_id = envelope.plan.agent.adapter_id
        self.digest = envelope.outcome.identity.adapter_digest
        self.cut_at = cut_at
        self.continuation = continuation
        self.stop_on_divergence = stop_on_divergence
        self.steps = recorded_steps(envelope)
        self.divergence: dict | None = None
        self.replayed = 0

    def manifest(self):
        return self.envelope.plan.agent

    async def act(self, session: TrialSession):
        recorded_intent = self.envelope.source_facts.get("intent") or {}
        identities = intent_mapping(recorded_intent, session.intent)
        evidence: dict[str, str] = {}
        for index, step in enumerate(self.steps):
            if self.cut_at is not None and index >= self.cut_at:
                break
            if step["kind"] == "wait":
                await session.wait(step["ticks"], caller="replay")
            elif step["kind"] == "call":
                call = step["call"]
                request = rebind(call.get("request") or {}, identities)
                before = len(session.observations)
                await session.call(call["tool"], request, caller="replay", hook=call.get("hook"))
                delivered = session.observations[before:]
                for recorded, fresh in zip(step["observations"], delivered):
                    evidence[recorded["evidence_id"]] = fresh.evidence_id
                self.replayed += 1
                expected = [shape(o) for o in step["observations"]]
                actual = [shape(o.model_dump(mode="json")) for o in delivered]
                if expected != actual:
                    self.divergence = {"step": index, "call_id": call["call_id"], "tool": call["tool"], "recorded": expected, "delivered": actual}
                    session.rule_step("replay", {"divergence": self.divergence})
                    if self.stop_on_divergence:
                        return None
            elif step["kind"] == "claim":
                report = rebind(rebind(step["report"], identities), evidence)
                return report
        if self.continuation is not None:
            return await self.continuation(session)
        return None


__all__ = ["ReplayAdapter", "intent_mapping", "rebind", "recorded_steps", "shape"]
