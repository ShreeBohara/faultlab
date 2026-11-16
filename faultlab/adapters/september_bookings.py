"""The September bookings agents (the correct one and the eight deliberately buggy ones) as v2 adapters.

Each adapter drives one September agent through the v2 session the way the September broker did: one actor turn
per action (charged as a $0 model call), the agent's view built from the session's own records
(``faultlab.packs.bookings.views``), the trusted request built from the intent (the agent chooses only a hold
label), and one report handed over exactly as the agent wrote it (``obs-N`` citations, hold labels). A buggy agent
is the correct one with one decision changed; running them through the lab shows that the checks still catch each
one there. An action the September broker would refuse as invalid ends the trial here (``ProtocolError``).
"""

from __future__ import annotations

from faultlab.adapters.base import AdapterSpec, BaseAdapter
from faultlab.core import content_hash
from faultlab.lab.session import ProtocolError
from faultlab.packs.bookings.pack import agent_request
from faultlab.packs.bookings.views import september_observations
from taskpacks.bookings_move_with_hold import driver, mutants, reference, table

PACK_ID = "bookings.move_with_hold/v1"
VERSION = "1"
INTENT_KEYS = ("task_id", "booking_id", "original_slot", "target_slot", "move_operation_id")


request_for = agent_request          # the trusted request is the pack's (faultlab.packs.bookings.pack.agent_request)


class _SeptemberAgentAdapter(BaseAdapter):
    agent_class = reference.ReferenceAgent

    async def act(self, session):
        agent = self.agent_class()
        intent = session.intent
        turns = session.caps.model_calls or table.DEFAULT_BUDGET["actor_calls"]
        while session.usage.model_calls < turns:
            session.model_call()
            view = {"task_text": table.TASK_TEXT, "turn": session.usage.model_calls, "turns_total": turns,
                    "intent": {key: intent[key] for key in INTENT_KEYS},
                    "observations": september_observations([o.model_dump(mode="json") for o in session.observations], session.calls)}
            action = agent.act(view)
            problem = driver.action_problem(action)
            if problem:
                raise ProtocolError(f"INVALID_ACTION: {problem}")
            if action["kind"] == "report":
                session.submit(action["report"])
                return None
            await session.call(action["tool"], request_for(action["tool"], action["args"], intent))
        return None


class ReferenceBookingsAdapter(_SeptemberAgentAdapter):
    spec = AdapterSpec(adapter_id="reference-bookings", version=VERSION, packs=[PACK_ID],
                       description="The September bookings reference agent: decides every turn from delivered evidence only.")


class BuggyBookingsAdapter(_SeptemberAgentAdapter):
    def __init__(self, name: str):
        if name not in mutants.MUTANTS:
            raise ValueError(f"Unknown buggy bookings agent {name!r}; known: {', '.join(mutants.MUTANTS)}")
        self.agent_class = mutants.MUTANTS[name]
        self.spec = AdapterSpec(adapter_id="buggy-bookings", version=VERSION, packs=[PACK_ID], settings_digest=content_hash({"mutant": name}),
                                description=f"The September bookings agent {name}: the reference with one decision changed.")


__all__ = ["BuggyBookingsAdapter", "ReferenceBookingsAdapter", "request_for"]
