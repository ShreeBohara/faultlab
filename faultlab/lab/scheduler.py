"""The scheduler (plan phase 1.5): a batch of plans becomes attempts; admission never exceeds the batch's caps.

``schedule`` expands every plan by its repetition policy into READY attempts in a declared
order and records the batch with its caps. ``Scheduler.next`` claims the next attempt for one
worker, after checking that what the batch has measured plus what its open attempts reserve
plus this attempt's own bound stays inside the batch caps. A plan without a dollar bound cannot
run in a batch that has one: the bound is what admission reasons about.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from faultlab.core import Caps, FaultLabError, StrictModel, new_id, utc_now_text
from faultlab.evidence.models import TrialAttempt, TrialPlan, plan_hash
from faultlab.lab.store import TrialStore

Order = Literal["repetition_major", "plan_major"]


class AdmissionRefused(FaultLabError):
    """Claiming the next attempt would exceed a batch cap; nothing was claimed."""


class Batch(StrictModel):
    batch_id: str
    name: str = Field(min_length=1, max_length=200)
    caps: Caps = Field(default_factory=Caps)
    order: Order = "repetition_major"
    plan_hashes: list[str] = Field(default_factory=list)
    created_at: str


def schedule(store: TrialStore, plans: list[TrialPlan], *, name: str, caps: Caps | None = None,
             order: Order = "repetition_major", batch_id: str | None = None) -> Batch:
    """Record the batch and one READY attempt per plan repetition, in the declared order."""
    if not plans:
        raise ValueError("A batch needs at least one plan")
    caps = caps or Caps()
    if caps.dollars is not None and any(plan.caps.dollars is None for plan in plans):
        raise ValueError("Every plan in a dollar-capped batch declares its own dollar bound")
    batch = Batch(batch_id=batch_id or new_id("batch"), name=name, caps=caps, order=order,
                  plan_hashes=[store.put_plan(plan) for plan in plans], created_at=utc_now_text())
    store.put_batch(batch.batch_id, batch.model_dump(mode="json"))
    sequence = []
    if order == "plan_major":
        for plan in plans:
            sequence.extend((plan, repetition) for repetition in range(plan.repetition.k))
    else:
        most = max(plan.repetition.k for plan in plans)
        for repetition in range(most):
            sequence.extend((plan, repetition) for plan in plans if repetition < plan.repetition.k)
    with store.transaction():
        for position, (plan, repetition) in enumerate(sequence):
            attempt = TrialAttempt(attempt_id=new_id("trial"), plan_hash=plan_hash(plan), lifecycle="READY")
            store.put_attempt(attempt, batch_id=batch.batch_id, position=position)
    return batch


class Scheduler:
    def __init__(self, store: TrialStore, batch_id: str, *, worker_id: str):
        self.store, self.batch_id, self.worker_id = store, batch_id, worker_id
        self.batch = Batch.model_validate(store.batch(batch_id))

    def admissible(self, plan: TrialPlan) -> tuple[bool, str | None]:
        caps = self.batch.caps
        spent = self.store.spent(batch_id=self.batch_id)
        if caps.dollars is not None:
            if plan.caps.dollars is None or spent["reserved"]["unbounded"]:
                return False, "UNBOUNDED_PLAN_IN_CAPPED_BATCH"
            if spent["measured"]["dollars"] + spent["reserved"]["dollars"] + plan.caps.dollars > caps.dollars:
                return False, "BATCH_DOLLAR_CAP"
        if caps.model_calls is not None:
            bound = plan.caps.model_calls
            if bound is None:
                return False, "UNBOUNDED_PLAN_IN_CAPPED_BATCH"
            if spent["measured"]["model_calls"] + spent["reserved"]["model_calls"] + bound > caps.model_calls:
                return False, "BATCH_MODEL_CALL_CAP"
        return True, None

    def next(self) -> tuple[TrialPlan, TrialAttempt] | None:
        """Claim the next READY attempt of the batch for this worker; refuse rather than exceed a cap."""
        with self.store.transaction():
            ready = self.store.attempts(batch_id=self.batch_id, lifecycle="READY")
            if not ready:
                return None
            plan = self.store.plan(ready[0].plan_hash)
            ok, why = self.admissible(plan)
            if not ok:
                raise AdmissionRefused(f"{why}: attempt {ready[0].attempt_id} of batch {self.batch_id}")
            claimed = self.store.claim(self.worker_id, batch_id=self.batch_id)
            return plan, claimed

    def pending(self) -> int:
        return len(self.store.attempts(batch_id=self.batch_id, lifecycle="READY"))


async def run_batch(store: TrialStore, batch_id: str, worker, adapter, *, stop_on_refusal: bool = True) -> list:
    """Drive one worker through a batch until it is empty or admission refuses; returns the envelopes."""
    scheduler = Scheduler(store, batch_id, worker_id=worker.worker_id)
    envelopes = []
    while True:
        try:
            item = scheduler.next()
        except AdmissionRefused:
            if stop_on_refusal:
                break
            raise
        if item is None:
            break
        plan, attempt = item
        envelopes.append(await worker.run(plan, attempt, adapter))
    return envelopes


__all__ = ["AdmissionRefused", "Batch", "Order", "Scheduler", "run_batch", "schedule"]
