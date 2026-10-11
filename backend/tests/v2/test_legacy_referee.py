"""The legacy orders checks score v2 trials through the bridge; the checker is called, never read."""
import asyncio

import pytest

from faultlab.core import IntegrityError
from faultlab.evidence import TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.referee.legacy import LegacyOrdersReferee
from test_lab_worker import AGENT, ENV, ORDERS, ScriptedOrdersAdapter, plan_for


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def worker(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield TrialWorker(store=store, worker_id="worker-legacy", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())


def test_the_scripted_agent_passes_all_eight_checks_on_every_development_scenario(worker):
    expected = {"dev-1": "COMPLETED", "dev-2": "COMPLETED", "dev-3": "COMPLETED", "dev-4": "COMPLETED",
                "dev-5": "CORRECTLY_REFUSED", "dev-6": "COMPLETED"}
    for scenario in ORDERS.scenarios:
        plan = plan_for(scenario.scenario_id)
        envelope = run(worker.run(plan, TrialAttempt(attempt_id=f"trial-{scenario.scenario_id}", plan_hash=plan_hash(plan), lifecycle="READY"),
                                  ScriptedOrdersAdapter()))
        assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == expected[scenario.scenario_id], scenario.scenario_id
        findings = envelope.outcome.findings
        assert [f.property_id for f in findings] == [f"C{n}" for n in range(1, 9)]
        assert all(f.result == "PASS" for f in findings), [(f.property_id, f.note) for f in findings if f.result != "PASS"]
        assert all(f.property_version == ORDERS.properties.checker_digest for f in findings)
        assert all(f.family == ORDERS.properties.properties[i].family for i, f in enumerate(findings))
        cited = {seq for f in findings for seq in f.witnesses}
        assert cited and all(envelope.events[seq].kind == "response_delivered" for seq in cited)
        assert envelope.outcome.claims.status == "SCORED" and envelope.outcome.claims.mismatches == []
        assert "TASK_OUTCOME_UNSCORED" not in envelope.source.notes


def test_a_false_success_claim_is_a_violation_on_both_the_checks_and_the_oracle(worker):
    class Liar:
        adapter_id = "scripted-orders"

        async def act(self, session):
            i = session.intent
            session.model_call()
            seen = await session.call("get_order", {"order_id": i["order_id"]})
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                    "evidence_ids": [seen.evidence_id], "next_action": {"kind": "NONE"}}

    plan = plan_for("dev-1")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-liar", plan_hash=plan_hash(plan), lifecycle="READY"), Liar()))
    assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == "VIOLATION"
    failed = {f.property_id for f in envelope.outcome.findings if f.result == "VIOLATION"}
    assert "C2" in failed or "C5" in failed, failed
    claims = envelope.outcome.claims
    assert claims.status == "SCORED" and "belief:upgrade_outcome" in claims.mismatches and "belief:notification_outcome" in claims.mismatches


def test_the_bridge_refuses_other_packs_and_an_unpinned_checker(worker):
    plan = plan_for("dev-1")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-ok", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    referee = LegacyOrdersReferee()
    from faultlab.lab.worker import ScoringContext
    context = ScoringContext(intent=envelope.source_facts["intent"], observations=[], decision={}, horizon={}, execution="COMPLETED")
    foreign = envelope.model_copy(update={"plan": envelope.plan.model_copy(update={"pack_id": "other/v1"})})
    with pytest.raises(IntegrityError, match="scores orders"):
        referee.score(foreign, context)
    with pytest.raises(IntegrityError, match="snapshots"):
        referee.score(envelope, context.model_copy(update={"decision": None}))
    # A plan that pins a different checker digest: the referee that ran is not the one pinned, so no verdict.
    other = plan.model_copy(update={"properties_digest": "e" * 64})
    sealed = run(worker.run(other, TrialAttempt(attempt_id="trial-unpinned", plan_hash=plan_hash(other), lifecycle="READY"), ScriptedOrdersAdapter()))
    assert sealed.outcome.execution == "PENDING_EVIDENCE" and sealed.outcome.task is None
    assert any(note.startswith("REFEREE_FAILED:IntegrityError") for note in sealed.source.notes)
